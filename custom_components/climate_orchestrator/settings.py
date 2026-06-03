"""Runtime tuning settings, backed by number/switch entities.

These descriptions drive both the number/switch platforms and the resolver the
coordinator uses each cycle. Values live on the entities (so the user adjusts
them at runtime and they persist); the resolver reads the current entity states
with a default fallback when an entity isn't present yet.
"""

from __future__ import annotations

from dataclasses import dataclass

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
    CALIBRATION_MODES,
    COMFORT_HUMIDITY_INFLUENCE_DEFAULT,
    COOL_OFF_OUTDOOR_DEFAULT,
    DEFAULT_CALIBRATION_MODE,
    DEFAULT_PRESETS,
    DEW_POINT_THRESHOLD_DEFAULT,
    DOMAIN,
    FROST_TEMP_DEFAULT,
    HEAT_OFF_OUTDOOR_DEFAULT,
    MAX_TEMP,
    MIN_TEMP,
    RELEASE_OFFSET_DEFAULT,
    SENSOR_MAX_AGE_DEFAULT,
    TARGET_TEMP_STEP,
    TOLERANCE_DEFAULT,
    VALVE_MAINTENANCE_INTERVAL_DEFAULT,
    WINDOW_OPEN_DELAY_DEFAULT,
)

_CALIBRATION_MODE_KEY = "calibration_mode"


def preset_number_key(preset: str, edge: str) -> str:
    """Number key for a preset's edge, e.g. ``preset_home_heat``."""
    return f"preset_{preset}_{edge}"


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
        "adaptive_comfort_max_shift", ADAPTIVE_COMFORT_MAX_SHIFT_DEFAULT, 0.0, 5.0, 0.5
    ),
    NumberSetting(
        "adaptive_comfort_bias", ADAPTIVE_COMFORT_BIAS_DEFAULT, -3.0, 3.0, 0.5
    ),
    NumberSetting(
        "adaptive_comfort_response", ADAPTIVE_COMFORT_RESPONSE_DEFAULT, 1.0, 10.0, 0.5
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

SWITCH_SETTINGS: tuple[SwitchSetting, ...] = (
    SwitchSetting("comfort_index_targeting", True),
    SwitchSetting("dew_point_guard", True),
    SwitchSetting("window_open_detection", True),
    SwitchSetting("ac_ignore_window", False),
    SwitchSetting("outdoor_temp_gating", True),
    SwitchSetting("frost_protection", True),
    SwitchSetting("ac_heating_assist", False),
    SwitchSetting("adaptive_ac_bias", True),
    SwitchSetting("auto_valve_maintenance", False),
    SwitchSetting("adaptive_comfort", False),
)


@dataclass(frozen=True, slots=True)
class RuntimeSettings:
    """Resolved values of every tuning entity for one control cycle."""

    release_offset: float
    tolerance: float
    comfort_humidity_influence: float
    frost_protection_temp: float
    dew_point_threshold: float
    heat_off_outdoor: float
    cool_off_outdoor: float
    ac_setpoint_bias: float
    ac_setpoint_bias_max: float
    adaptive_comfort_max_shift: float
    adaptive_comfort_bias: float
    adaptive_comfort_response: float
    window_open_delay: float
    valve_maintenance_interval: float
    sensor_max_age: float
    comfort_index_targeting: bool
    dew_point_guard: bool
    window_open_detection: bool
    ac_ignore_window: bool
    outdoor_temp_gating: bool
    frost_protection: bool
    ac_heating_assist: bool
    adaptive_ac_bias: bool
    auto_valve_maintenance: bool
    adaptive_comfort: bool
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
    state = hass.states.get(entity_id) if entity_id else None
    if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
        return default
    try:
        return float(state.state)
    except (TypeError, ValueError):
        return default


@callback
def _number_value(hass: HomeAssistant, entry_id: str, setting: NumberSetting) -> float:
    return number_value(hass, entry_id, setting.key, setting.default)


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
    return (low, high)


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
    """Read the current value of every tuning entity (default if absent)."""
    numbers = {s.key: _number_value(hass, entry_id, s) for s in NUMBER_SETTINGS}
    switches = {s.key: _switch_value(hass, entry_id, s) for s in SWITCH_SETTINGS}
    return RuntimeSettings(
        release_offset=numbers["release_offset"],
        tolerance=numbers["tolerance"],
        comfort_humidity_influence=numbers["comfort_humidity_influence"],
        frost_protection_temp=numbers["frost_protection_temp"],
        dew_point_threshold=numbers["dew_point_threshold"],
        heat_off_outdoor=numbers["heat_off_outdoor"],
        cool_off_outdoor=numbers["cool_off_outdoor"],
        ac_setpoint_bias=numbers["ac_setpoint_bias"],
        ac_setpoint_bias_max=numbers["ac_setpoint_bias_max"],
        adaptive_comfort_max_shift=numbers["adaptive_comfort_max_shift"],
        adaptive_comfort_bias=numbers["adaptive_comfort_bias"],
        adaptive_comfort_response=numbers["adaptive_comfort_response"],
        window_open_delay=numbers["window_open_delay"],
        valve_maintenance_interval=numbers["valve_maintenance_interval"],
        sensor_max_age=numbers["sensor_max_age"],
        comfort_index_targeting=switches["comfort_index_targeting"],
        dew_point_guard=switches["dew_point_guard"],
        window_open_detection=switches["window_open_detection"],
        ac_ignore_window=switches["ac_ignore_window"],
        outdoor_temp_gating=switches["outdoor_temp_gating"],
        frost_protection=switches["frost_protection"],
        ac_heating_assist=switches["ac_heating_assist"],
        adaptive_ac_bias=switches["adaptive_ac_bias"],
        auto_valve_maintenance=switches["auto_valve_maintenance"],
        adaptive_comfort=switches["adaptive_comfort"],
        calibration_mode=_calibration_mode(hass, entry_id),
    )
