"""Runtime tuning settings, backed by number/switch entities.

These descriptions drive both the number/switch platforms and the resolver the
coordinator uses each cycle. Values live on the entities (so the user adjusts
them at runtime and they persist); the resolver reads the current entity states
with a default fallback when an entity isn't present yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.const import (
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er

from .const import (
    AC_SETPOINT_BIAS_DEFAULT,
    AC_SETPOINT_BIAS_MAX_DEFAULT,
    ADAPTIVE_COMFORT_BIAS_DEFAULT,
    ADAPTIVE_COMFORT_MAX_SHIFT_DEFAULT,
    ADAPTIVE_COMFORT_RESPONSE_DEFAULT,
    AREA_BAND_OFFSET_DEFAULT,
    AREA_BAND_OFFSET_LIMIT,
    BOOST_DURATION_DEFAULT,
    BOOST_DURATION_MAX,
    BOOST_OFFSET_DEFAULT,
    BOOST_OFFSET_MAX,
    CALIBRATION_MODES,
    COMFORT_HUMIDITY_INFLUENCE_DEFAULT,
    CONF_PRESETS,
    COOL_OFF_OUTDOOR_DEFAULT,
    DEFAULT_CALIBRATION_MODE,
    DEFAULT_PRESETS,
    DEW_POINT_THRESHOLD_DEFAULT,
    DOMAIN,
    FROST_TEMP_DEFAULT,
    HEAT_OFF_OUTDOOR_DEFAULT,
    MANUAL_OVERRIDE_DURATION_DEFAULT,
    MANUAL_OVERRIDE_DURATION_MAX,
    MAX_TEMP,
    MIN_TEMP,
    PRECONDITION_HORIZON_DEFAULT,
    RELEASE_OFFSET_DEFAULT,
    SELECTABLE_PRESETS,
    SENSOR_MAX_AGE_DEFAULT,
    TARGET_TEMP_STEP,
    TOLERANCE_DEFAULT,
    VALVE_MAINTENANCE_INTERVAL_DEFAULT,
    WINDOW_OPEN_DELAY_DEFAULT,
)
from .control.numeric import clamp
from .util import float_state

if TYPE_CHECKING:
    from collections.abc import Mapping

_CALIBRATION_MODE_KEY = "calibration_mode"


def preset_number_key(preset: str, edge: str) -> str:
    """Build the number key for a preset's edge, e.g. ``preset_home_heat``."""
    return f"preset_{preset}_{edge}"


def enabled_presets(options: Mapping[str, Any]) -> list[str]:
    """Named presets the user chose to expose (merged entry data + options).

    Unset (or anything malformed) means **all** — preset selection is opt-in
    narrowing. Order and validity come from ``SELECTABLE_PRESETS``, so unknown
    values are dropped and the result is stable regardless of how the
    selection was stored. ``manual`` is not listed here; it is always
    available on the climate entity.
    """
    value = options.get(CONF_PRESETS)
    if not isinstance(value, list):
        return list(SELECTABLE_PRESETS)
    return [preset for preset in SELECTABLE_PRESETS if preset in value]


def area_offset_key(area_id: str) -> str:
    """Build the area's comfort-band-offset key, e.g. ``area_offset_kitchen``."""
    return f"area_offset_{area_id}"


@dataclass(frozen=True, slots=True)
class NumberSetting:
    """A numeric, user-adjustable control parameter."""

    key: str
    default: float
    min_value: float
    max_value: float
    step: float
    unit: str | None = UnitOfTemperature.CELSIUS


@dataclass(frozen=True, slots=True)
class SwitchSetting:
    """A boolean, user-toggleable feature flag."""

    key: str
    default: bool


NUMBER_SETTINGS: tuple[NumberSetting, ...] = (
    NumberSetting("release_offset", RELEASE_OFFSET_DEFAULT, 0.0, 3.0, 0.1),
    NumberSetting("tolerance", TOLERANCE_DEFAULT, 0.0, 2.0, 0.1),
    NumberSetting(
        "comfort_humidity_influence",
        COMFORT_HUMIDITY_INFLUENCE_DEFAULT,
        0.0,
        2.0,
        0.1,
        unit=None,
    ),
    NumberSetting("frost_protection_temp", FROST_TEMP_DEFAULT, 3.0, 12.0, 0.5),
    NumberSetting("dew_point_threshold", DEW_POINT_THRESHOLD_DEFAULT, 10.0, 22.0, 0.5),
    NumberSetting("heat_off_outdoor", HEAT_OFF_OUTDOOR_DEFAULT, 5.0, 30.0, 0.5),
    NumberSetting("cool_off_outdoor", COOL_OFF_OUTDOOR_DEFAULT, 0.0, 25.0, 0.5),
    NumberSetting("ac_setpoint_bias", AC_SETPOINT_BIAS_DEFAULT, 0.0, 5.0, 0.5),
    NumberSetting("ac_setpoint_bias_max", AC_SETPOINT_BIAS_MAX_DEFAULT, 0.5, 8.0, 0.5),
    NumberSetting(
        "adaptive_cooling_comfort_max_shift",
        ADAPTIVE_COMFORT_MAX_SHIFT_DEFAULT,
        0.0,
        5.0,
        0.5,
    ),
    NumberSetting(
        "adaptive_cooling_comfort_onset_bias",
        ADAPTIVE_COMFORT_BIAS_DEFAULT,
        -3.0,
        3.0,
        0.5,
    ),
    NumberSetting(
        "adaptive_cooling_comfort_response",
        ADAPTIVE_COMFORT_RESPONSE_DEFAULT,
        1.0,
        10.0,
        0.5,
    ),
    NumberSetting(
        "window_open_delay",
        WINDOW_OPEN_DELAY_DEFAULT,
        0.0,
        30.0,
        0.5,
        unit=UnitOfTime.MINUTES,
    ),
    NumberSetting(
        "valve_maintenance_interval",
        VALVE_MAINTENANCE_INTERVAL_DEFAULT,
        1.0,
        60.0,
        1.0,
        unit=UnitOfTime.DAYS,
    ),
    NumberSetting(
        "sensor_max_age",
        SENSOR_MAX_AGE_DEFAULT,
        0.0,
        720.0,
        5.0,
        unit=UnitOfTime.MINUTES,
    ),
    NumberSetting(
        "preconditioning_horizon",
        PRECONDITION_HORIZON_DEFAULT,
        0.5,
        8.0,
        0.5,
        unit=UnitOfTime.HOURS,
    ),
    NumberSetting(
        "manual_override_duration",
        MANUAL_OVERRIDE_DURATION_DEFAULT,
        0.0,
        MANUAL_OVERRIDE_DURATION_MAX,
        5.0,
        unit=UnitOfTime.MINUTES,
    ),
)

# Editable per-preset band edges: heat-below and cool-above for each preset.
PRESET_NUMBER_SETTINGS: tuple[NumberSetting, ...] = tuple(
    NumberSetting(
        preset_number_key(preset, edge),
        default=low if edge == "heat" else high,
        min_value=MIN_TEMP,
        max_value=MAX_TEMP,
        step=TARGET_TEMP_STEP,
    )
    for preset, (low, high) in DEFAULT_PRESETS.items()
    for edge in ("heat", "cool")
)

# Boost tunables (created only when the boost preset is selected): how far the
# demanded band edge is pushed, and how long until the auto-revert.
BOOST_NUMBER_SETTINGS: tuple[NumberSetting, ...] = (
    NumberSetting(
        "boost_offset",
        BOOST_OFFSET_DEFAULT,
        0.5,
        BOOST_OFFSET_MAX,
        TARGET_TEMP_STEP,
        unit=UnitOfTemperature.CELSIUS,
    ),
    NumberSetting(
        "boost_duration",
        BOOST_DURATION_DEFAULT,
        5.0,
        BOOST_DURATION_MAX,
        5.0,
        unit=UnitOfTime.MINUTES,
    ),
)

SWITCH_SETTINGS: tuple[SwitchSetting, ...] = (
    SwitchSetting("comfort_index_targeting", True),
    SwitchSetting("home_average_trigger", True),
    SwitchSetting("dew_point_guard", True),
    SwitchSetting("window_open_detection", True),
    SwitchSetting("ac_ignore_window", False),
    SwitchSetting("outdoor_temp_gating", True),
    SwitchSetting("frost_protection", True),
    SwitchSetting("ac_heating_assist", False),
    SwitchSetting("self_tuning_ac_bias", True),
    SwitchSetting("auto_valve_maintenance", False),
    SwitchSetting("adaptive_cooling_comfort", False),
    SwitchSetting("forecast_preconditioning", False),
    SwitchSetting("event_notifications", True),
)


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Resolved values of every tuning entity for one control cycle.

    Field names must match the ``NUMBER_SETTINGS``/``SWITCH_SETTINGS`` keys
    one-to-one (plus ``calibration_mode``): ``resolve_settings`` constructs
    this directly from the registries, so a mismatch fails loudly on the
    first control cycle — and is pinned by ``test_settings``.
    """

    release_offset: float
    tolerance: float
    comfort_humidity_influence: float
    frost_protection_temp: float
    dew_point_threshold: float
    heat_off_outdoor: float
    cool_off_outdoor: float
    ac_setpoint_bias: float
    ac_setpoint_bias_max: float
    adaptive_cooling_comfort_max_shift: float
    adaptive_cooling_comfort_onset_bias: float
    adaptive_cooling_comfort_response: float
    window_open_delay: float
    valve_maintenance_interval: float
    sensor_max_age: float
    preconditioning_horizon: float
    manual_override_duration: float
    comfort_index_targeting: bool
    home_average_trigger: bool
    dew_point_guard: bool
    window_open_detection: bool
    ac_ignore_window: bool
    outdoor_temp_gating: bool
    frost_protection: bool
    ac_heating_assist: bool
    self_tuning_ac_bias: bool
    auto_valve_maintenance: bool
    adaptive_cooling_comfort: bool
    forecast_preconditioning: bool
    event_notifications: bool
    calibration_mode: str


@callback
def _calibration_mode(hass: HomeAssistant, entry_id: str) -> str:
    entity_id = er.async_get(hass).async_get_entity_id(
        "select", DOMAIN, f"{entry_id}_{_CALIBRATION_MODE_KEY}"
    )
    state = hass.states.get(entity_id) if entity_id else None
    if state is None or state.state not in CALIBRATION_MODES:
        return DEFAULT_CALIBRATION_MODE
    return state.state


@callback
def number_value(hass: HomeAssistant, entry_id: str, key: str, default: float) -> float:
    """Read a number entity's value by key, falling back to ``default``."""
    entity_id = er.async_get(hass).async_get_entity_id(
        "number", DOMAIN, f"{entry_id}_{key}"
    )
    value = float_state(hass, entity_id)
    return default if value is None else value


@callback
def _number_value(hass: HomeAssistant, entry_id: str, setting: NumberSetting) -> float:
    # Clamp to the declared bounds: Developer Tools (and a restored state from
    # an older release with wider limits) can hold values the UI would refuse.
    value = number_value(hass, entry_id, setting.key, setting.default)
    return clamp(value, setting.min_value, setting.max_value)


_NUMBER_SETTINGS_BY_KEY = {s.key: s for s in (*NUMBER_SETTINGS, *BOOST_NUMBER_SETTINGS)}


@callback
def clamped_number_value(hass: HomeAssistant, entry_id: str, key: str) -> float:
    """Read a registry number setting, clamped to its declared bounds."""
    return _number_value(hass, entry_id, _NUMBER_SETTINGS_BY_KEY[key])


@callback
def preset_band(
    hass: HomeAssistant, entry_id: str, preset: str
) -> tuple[float, float] | None:
    """Live (heat_edge, cool_edge) for a preset from its number entities."""
    edges = DEFAULT_PRESETS.get(preset)
    if edges is None:
        return None
    low = number_value(hass, entry_id, preset_number_key(preset, "heat"), edges[0])
    high = number_value(hass, entry_id, preset_number_key(preset, "cool"), edges[1])
    return (clamp(low, MIN_TEMP, MAX_TEMP), clamp(high, MIN_TEMP, MAX_TEMP))


@callback
def area_band_offset(hass: HomeAssistant, entry_id: str, area_id: str | None) -> float:
    """Live comfort band offset (°C) for an area, ``0`` when none is set."""
    if area_id is None:
        return AREA_BAND_OFFSET_DEFAULT
    offset = number_value(
        hass, entry_id, area_offset_key(area_id), AREA_BAND_OFFSET_DEFAULT
    )
    return clamp(offset, -AREA_BAND_OFFSET_LIMIT, AREA_BAND_OFFSET_LIMIT)


@callback
def _switch_value(hass: HomeAssistant, entry_id: str, setting: SwitchSetting) -> bool:
    entity_id = er.async_get(hass).async_get_entity_id(
        "switch", DOMAIN, f"{entry_id}_{setting.key}"
    )
    state = hass.states.get(entity_id) if entity_id else None
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return setting.default
    return state.state == "on"


@callback
def resolve_settings(hass: HomeAssistant, entry_id: str) -> RuntimeSettings:
    """Read the current value of every tuning entity (default if absent).

    Driven entirely by the setting registries — the registry keys *are* the
    ``RuntimeSettings`` field names, so adding a setting means adding the
    registry entry and the typed field, nothing else. Any drift between the
    two raises ``TypeError`` here (missing or unexpected keyword).
    """
    values: dict[str, Any] = {
        s.key: _number_value(hass, entry_id, s) for s in NUMBER_SETTINGS
    }
    values |= {s.key: _switch_value(hass, entry_id, s) for s in SWITCH_SETTINGS}
    values["calibration_mode"] = _calibration_mode(hass, entry_id)
    return RuntimeSettings(**values)
