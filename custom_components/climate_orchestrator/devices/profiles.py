"""Per-device behaviour profiles: the seam for hardware quirks.

A ``DeviceProfile`` captures everything that varies between climate devices —
which attributes carry the room temperature and setpoint, how to read
capabilities, and which ``number`` entities back valve/calibration control — as
a plain value object rather than conditionals scattered through the adapter and
coordinator. The default ``GENERIC`` profile reproduces the integration's
historical behaviour exactly; concrete profiles override only what differs and
are matched by ``(integration, manufacturer, model)`` from the device registry.

See ``docs/decisions/0001-device-profiles.md`` for the rationale, and
``docs/project/adding-hardware.md`` for how to add a profile.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from ..const import MAX_TEMP, MIN_TEMP, TARGET_TEMP_STEP
from ..util import as_float
from .model import AdapterCapabilities, DeviceState
from .trv import LOCAL_CALIBRATION_HINTS, VALVE_OPENING_HINTS

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping

    from homeassistant.core import HomeAssistant


@dataclass(frozen=True, slots=True)
class DeviceProfile:
    """How to read and discover one class of climate device.

    All fields default to the standard Home Assistant climate contract, so the
    bare ``DeviceProfile()`` *is* the generic profile. A concrete profile sets
    only the fields that differ for its hardware.
    """

    name: str = "generic"
    # Attribute names carrying the room temperature and the active setpoint.
    current_temp_attr: str = "current_temperature"
    target_temp_attr: str = "temperature"
    # Per-model valve / local-calibration number-name hints. ``None`` defers to
    # the user-configured (or global default) hints; a tuple overrides them.
    valve_hints: tuple[str, ...] | None = None
    calibration_hints: tuple[str, ...] | None = None

    def read(self, state: str | None, attrs: Mapping[str, Any]) -> DeviceState:
        """Snapshot the device from its raw state string and attributes."""
        if state is None or state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return DeviceState(
                available=False, hvac_mode=None, current_temp=None, target_temp=None
            )
        return DeviceState(
            available=True,
            hvac_mode=state,
            current_temp=as_float(attrs.get(self.current_temp_attr)),
            target_temp=as_float(attrs.get(self.target_temp_attr)),
        )

    def capabilities(self, attrs: Mapping[str, Any]) -> AdapterCapabilities:
        """Detect what the device supports from its reported attributes."""
        modes = attrs.get("hvac_modes") or []
        return AdapterCapabilities(
            can_heat="heat" in modes,
            can_cool="cool" in modes,
            can_dry="dry" in modes,
            min_temp=attrs.get("min_temp", MIN_TEMP),
            max_temp=attrs.get("max_temp", MAX_TEMP),
            target_step=attrs.get("target_temp_step", TARGET_TEMP_STEP),
        )

    def resolve_valve_hints(self, configured: tuple[str, ...]) -> tuple[str, ...]:
        """Valve-number hints for this device (profile override, else config)."""
        return self.valve_hints if self.valve_hints is not None else configured

    def resolve_calibration_hints(self, configured: tuple[str, ...]) -> tuple[str, ...]:
        """Calibration-number hints for this device (profile override, else config)."""
        return (
            self.calibration_hints if self.calibration_hints is not None else configured
        )


# The default: the standard climate contract, i.e. today's behaviour.
GENERIC = DeviceProfile()

# SONOFF TRVZB — the radiator valve this integration was built against. It
# speaks the standard climate contract, so only its discovery hints differ from
# generic (the canonical Zigbee2MQTT number names). Reusing the shared hint
# tuples keeps behaviour identical to the pre-profile defaults.
SONOFF_TRVZB = DeviceProfile(
    name="sonoff_trvzb",
    valve_hints=VALVE_OPENING_HINTS,
    calibration_hints=LOCAL_CALIBRATION_HINTS,
)


def _is_sonoff_trvzb(
    _integration: str | None, _manufacturer: str | None, model: str | None
) -> bool:
    """Match the SONOFF TRVZB by model, however the integration reports make."""
    return model is not None and "trvzb" in model


# A matcher takes the lower-cased (integration, manufacturer, model) and says
# whether its profile applies. Tried in order; first match wins, GENERIC is the
# implicit fallback. Concrete entries are added as hardware support lands.
_PROFILES: tuple[tuple[Callable[..., bool], DeviceProfile], ...] = (
    (_is_sonoff_trvzb, SONOFF_TRVZB),
)


def resolve_profile(
    *,
    integration: str | None,
    manufacturer: str | None,
    model: str | None,
) -> DeviceProfile:
    """Pick the profile for a device's identity, or ``GENERIC`` if none match."""
    ints = integration.lower() if integration else None
    manu = manufacturer.lower() if manufacturer else None
    mod = model.lower() if model else None
    for matches, profile in _PROFILES:
        if matches(ints, manu, mod):
            return profile
    return GENERIC


def profile_for_entity(hass: HomeAssistant, entity_id: str) -> DeviceProfile:
    """Resolve the profile for a climate entity via the device registry."""
    ent_reg = er.async_get(hass)
    entry = ent_reg.async_get(entity_id)
    if entry is None:
        return GENERIC
    manufacturer: str | None = None
    model: str | None = None
    if entry.device_id is not None:
        device = dr.async_get(hass).async_get(entry.device_id)
        if device is not None:
            manufacturer = device.manufacturer
            model = device.model
    return resolve_profile(
        integration=entry.platform, manufacturer=manufacturer, model=model
    )
