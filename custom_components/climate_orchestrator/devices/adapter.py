"""Adapter that drives a Home Assistant ``climate`` entity.

Works for any climate entity (TRV or AC) since both expose the standard climate
services. Capabilities are detected from the entity's reported attributes, and
commands are applied via the minimal set of service calls (see reconcile).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE

from .model import AdapterCapabilities, DeviceCommand, DeviceState
from .profiles import profile_for_entity
from .reconcile import reconcile

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .profiles import DeviceProfile


class ClimateAdapter:
    """Read and command a single Home Assistant climate entity.

    Stateless: a thin wrapper over state reads and service calls, meant to
    be instantiated per use (the coordinator creates one per device per
    cycle) — do not cache instances expecting them to track state.

    All device-specific behaviour (which attributes to read, capability
    quirks) lives in the resolved ``DeviceProfile``, not here.
    """

    def __init__(
        self, hass: HomeAssistant, entity_id: str, profile: DeviceProfile | None = None
    ) -> None:
        """Bind the adapter to an entity (and its hardware profile)."""
        self.hass = hass
        self.entity_id = entity_id
        self.profile = (
            profile if profile is not None else profile_for_entity(hass, entity_id)
        )

    def read(self) -> DeviceState:
        """Snapshot the device's current state."""
        state = self.hass.states.get(self.entity_id)
        if state is None:
            return DeviceState(
                available=False, hvac_mode=None, current_temp=None, target_temp=None
            )
        return self.profile.read(state.state, state.attributes)

    def capabilities(self) -> AdapterCapabilities:
        """Detect what the device supports from its reported attributes."""
        state = self.hass.states.get(self.entity_id)
        attrs = state.attributes if state is not None else {}
        return self.profile.capabilities(attrs)

    async def apply(self, command: DeviceCommand) -> None:
        """Issue the minimal service calls to reach ``command``."""
        state = self.read()
        if not state.available:
            return

        writes = reconcile(state, command, step=self.capabilities().target_step)
        if writes.set_hvac_mode is not None:
            await self.hass.services.async_call(
                CLIMATE_DOMAIN,
                SERVICE_SET_HVAC_MODE,
                {
                    ATTR_ENTITY_ID: self.entity_id,
                    ATTR_HVAC_MODE: writes.set_hvac_mode.value,
                },
                blocking=True,
            )
        if writes.set_temperature is not None:
            await self.hass.services.async_call(
                CLIMATE_DOMAIN,
                SERVICE_SET_TEMPERATURE,
                {
                    ATTR_ENTITY_ID: self.entity_id,
                    ATTR_TEMPERATURE: writes.set_temperature,
                },
                blocking=True,
            )
