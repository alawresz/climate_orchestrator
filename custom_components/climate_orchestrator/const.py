"""Constants for the Climate Orchestrator integration."""

from __future__ import annotations

from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "climate_orchestrator"

# Title used for the single whole-home config entry and hub device.
DEFAULT_TITLE: Final = "Climate Orchestrator"
MANUFACTURER: Final = "Climate Orchestrator"
MODEL: Final = "Whole-home orchestrator"

PLATFORMS: Final[list[Platform]] = [
    Platform.BINARY_SENSOR,
    Platform.CLIMATE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

# --- Configuration keys (stored in entry.data / entry.options) ---------------
CONF_TRVS: Final = "trvs"
CONF_ACS: Final = "acs"
CONF_OUTDOOR_SENSOR: Final = "outdoor_sensor"
CONF_WEATHER_ENTITY: Final = "weather_entity"
# Name hints (comma-separated, set in the options UI) used to discover a TRV's
# valve-opening and local-calibration `number` entities for mpc/offset modes.
# Defaults target Zigbee2MQTT naming; override for other brands/firmware.
CONF_VALVE_HINTS: Final = "valve_opening_hints"
CONF_CALIBRATION_HINTS: Final = "calibration_hints"

# --- Control surface defaults ------------------------------------------------
TARGET_TEMP_STEP: Final = 0.5
MIN_TEMP: Final = 7.0
MAX_TEMP: Final = 35.0

# How often to re-evaluate even with no state changes (keepalive).
UPDATE_INTERVAL_SECONDS: Final = 60

# --- Presets -----------------------------------------------------------------
# Each preset is a comfort band defined by its two edges: heat below `min`,
# cool above `max` (see DESIGN.md §7). These are Phase 1 defaults; they become
# editable `number` entities in a later phase.
PRESET_MANUAL: Final = "manual"
DEFAULT_PRESETS: Final[dict[str, tuple[float, float]]] = {
    "away": (16.0, 30.0),
    "home": (20.5, 24.5),
    "sleep": (19.5, 23.5),
}
DEFAULT_PRESET: Final = "home"
PRESET_MODES: Final[list[str]] = [*DEFAULT_PRESETS, PRESET_MANUAL]

# --- Control defaults --------------------------------------------------------
RELEASE_OFFSET_DEFAULT: Final = 0.5
# Minimum margin past a band edge before engaging (anti short-cycle deadband).
TOLERANCE_DEFAULT: Final = 0.3
# Blend factor on the comfort index: effective = dry_bulb + k * (apparent -
# dry_bulb). 0 ignores humidity, 1 is full apparent temperature, >1 amplifies.
COMFORT_HUMIDITY_INFLUENCE_DEFAULT: Final = 1.0
FROST_TEMP_DEFAULT: Final = 7.0
DEW_POINT_THRESHOLD_DEFAULT: Final = 16.0
HEAT_OFF_OUTDOOR_DEFAULT: Final = 20.0
COOL_OFF_OUTDOOR_DEFAULT: Final = 16.0
# How far below the real target to bias an AC's setpoint so its own sensor
# doesn't satisfy before the room does (DESIGN.md §6.2).
AC_SETPOINT_BIAS_DEFAULT: Final = 1.5
# Adaptive AC bias (integral feedback): ceiling on total bias, integral gain
# (°C added per °C-minute of error), and decay applied when not cooling.
AC_SETPOINT_BIAS_MAX_DEFAULT: Final = 4.0
ADAPTIVE_BIAS_KI: Final = 0.05
ADAPTIVE_BIAS_DECAY: Final = 0.5
# When cooling is wanted, force the AC's setpoint at least this far below the
# AC's *own* internal sensor, so the compressor actually runs (it idles/fans if
# the setpoint isn't below what it reads). The room sensor still decides when to
# stop. See DESIGN.md §6.2.
AC_COOL_KICK: Final = 1.0

# AC setpoint write throttling: the proportional compressor anchor nudges the
# commanded setpoint most cycles, so re-write it only when it has moved at least
# this much AND this long has elapsed since the last write, with a periodic
# keep-alive re-assert so the device never drifts away unnoticed.
AC_SETPOINT_MIN_CHANGE: Final = 0.5
AC_SETPOINT_MIN_INTERVAL_SECONDS: Final = 180.0
AC_SETPOINT_KEEPALIVE_SECONDS: Final = 900.0

# Adaptive comfort: max cool-edge shift (°C), the onset bias (°C) relative to
# the cool edge, the smoothing "response" (°C of outdoor excess for ~63% of the
# cap), and the running-mean-outdoor time constant (seconds) for the
# exponential smoother (~1 day of memory).
ADAPTIVE_COMFORT_MAX_SHIFT_DEFAULT: Final = 2.0
ADAPTIVE_COMFORT_BIAS_DEFAULT: Final = 1.0
ADAPTIVE_COMFORT_RESPONSE_DEFAULT: Final = 5.0
RMOT_TAU_SECONDS: Final = 86400.0

# Treat an area sensor whose value is older than this (minutes) as missing, so a
# frozen-but-"available" sensor can't drive control on stale data. 0 disables.
SENSOR_MAX_AGE_DEFAULT: Final = 360.0
# Trailing window (seconds) for the per-device cycle/runtime counters.
RUNTIME_WINDOW_SECONDS: Final = 3600.0

# Valve maintenance: exercise each TRV valve fully open then closed to stop it
# seizing/scaling. Dwell is how long to hold each extreme; interval is the
# auto-maintenance cadence in days.
VALVE_MAINTENANCE_DWELL_SECONDS: Final = 30.0
VALVE_MAINTENANCE_INTERVAL_DEFAULT: Final = 30.0

# Service names.
SERVICE_RESET_MPC_LEARNING: Final = "reset_mpc_learning"
SERVICE_RUN_VALVE_MAINTENANCE: Final = "run_valve_maintenance"
# Grace period (minutes) a window may stay open before heating/cooling stops;
# 0 = stop immediately (DESIGN.md §6.5).
WINDOW_OPEN_DELAY_DEFAULT: Final = 0.0

# --- TRV calibration strategy ------------------------------------------------
CALIBRATION_TARGET: Final = "target"  # set the TRV's mode + setpoint (default)
CALIBRATION_MPC: Final = "mpc"  # drive the TRV valve opening via MPC
CALIBRATION_OFFSET: Final = "offset"  # bias the TRV's local temperature
CALIBRATION_MODES: Final[list[str]] = [
    CALIBRATION_TARGET,
    CALIBRATION_MPC,
    CALIBRATION_OFFSET,
]
DEFAULT_CALIBRATION_MODE: Final = CALIBRATION_TARGET
