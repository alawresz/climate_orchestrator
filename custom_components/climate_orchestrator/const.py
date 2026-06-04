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

# Config entry schema version (kept in lock-step with the config flow's
# VERSION; bump together with a migration step in __init__.async_migrate_entry).
CONFIG_ENTRY_VERSION: Final = 1

# --- Configuration keys (stored in entry.data / entry.options) ---------------
CONF_TRVS: Final = "trvs"
CONF_ACS: Final = "acs"
CONF_OUTDOOR_SENSOR: Final = "outdoor_sensor"
CONF_WEATHER_ENTITY: Final = "weather_entity"
# Optional user-provided whole-home average sensors. When set they override the
# internally computed mean of the managed areas' sensors (e.g. to include rooms
# without managed devices); if an override is unavailable/stale, the computed
# mean stands in and the home_avg_source diagnostic reports the fallback.
CONF_HOME_TEMP_SENSOR: Final = "home_temperature_sensor"
CONF_HOME_HUMIDITY_SENSOR: Final = "home_humidity_sensor"
# Name hints (comma-separated, set in the options UI) used to discover a TRV's
# valve-opening and local-calibration `number` entities for mpc/offset modes.
# Defaults target Zigbee2MQTT naming; override for other brands/firmware.
CONF_VALVE_HINTS: Final = "valve_opening_hints"
CONF_CALIBRATION_HINTS: Final = "calibration_hints"
# Which named presets to expose (subset of DEFAULT_PRESETS; "manual" is always
# available). Unset means all — selecting fewer drops the unused presets from
# the climate entity and skips creating their setpoint number entities.
CONF_PRESETS: Final = "presets"

# --- Control surface defaults ------------------------------------------------
TARGET_TEMP_STEP: Final = 0.5
MIN_TEMP: Final = 7.0
MAX_TEMP: Final = 35.0

# Per-area comfort band offset (°C). A positive value shifts that area's whole
# band up — it heats sooner and releases later, so the room runs warmer; a
# negative value runs it cooler. Default 0 = no shift. Bounded so a single area
# can't be nudged absurdly far from the home band.
AREA_BAND_OFFSET_DEFAULT: Final = 0.0
AREA_BAND_OFFSET_LIMIT: Final = 5.0

# How often to re-evaluate even with no state changes (keepalive).
UPDATE_INTERVAL_SECONDS: Final = 60

# Forecast-based preconditioning (MPC TRVs only). When enabled, the weather
# entity's hourly forecast is fed into the valve optimisation over this look-ahead
# so a radiator can start warming a room ahead of a cold spell. The forecast is
# refreshed at most this often; the look-ahead is interpolated to the control
# step and capped at a safe number of steps.
PRECONDITION_HORIZON_DEFAULT: Final = 2.0  # hours
PRECONDITION_FORECAST_REFRESH_SECONDS: Final = 900.0
PRECONDITION_MAX_STEPS: Final = 600

# A single control-cycle failure is contained by design (logged, retried next
# cycle). This many *consecutive* failures means devices are no longer being
# commanded at all — surface a repair instead of failing silently in the log.
CONTROL_FAILURE_ISSUE_THRESHOLD: Final = 3

# Post-restart warm-up window. Until a managed device first reports a usable
# temperature, the orchestrator reports ``initializing`` for this long and holds
# back transient repairs (no temperature source, stale sensor) — sensors often
# take tens of seconds to report in after a Home Assistant restart. Once the
# window elapses with still no reading, the missing-source repair is genuine.
STARTUP_GRACE_SECONDS: Final = 120.0

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

# Boost: a temporary override preset (HA's standard "boost"), not a band of its
# own — it takes the previous preset's band and pushes the demanded edge by
# **Boost offset** for **Boost duration**, then reverts automatically. The big
# band error makes MPC/AC drive hard while every guard (window, frost, outdoor
# gating) stays active.
PRESET_BOOST: Final = "boost"
BOOST_OFFSET_DEFAULT: Final = 2.0  # °C the demanded edge is pushed
BOOST_OFFSET_MAX: Final = 5.0
BOOST_DURATION_DEFAULT: Final = 30.0  # minutes until auto-revert
BOOST_DURATION_MAX: Final = 240.0

# Everything offered in the config flow's preset multi-select ("manual" is not
# selectable: it's just "the user touched the setpoints" and always available).
SELECTABLE_PRESETS: Final[list[str]] = [*DEFAULT_PRESETS, PRESET_BOOST]

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
