"""Coordinator for the Climate Orchestrator integration.

Owns the shared runtime snapshot and the control cycle. In Phase 1 the cycle
just resolves sensors and aggregates; control logic lands in later phases. It is
event-driven (state-change listeners over the managed devices and their area
sensors) with a periodic keepalive, and re-subscribes when the tracked set
changes.
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass, field, replace
from datetime import timedelta
import logging
import math
import time
from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import HVACMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.exceptions import UnsupportedStorageVersionError
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.helpers import (
    issue_registry as ir,
)
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
)
from homeassistant.helpers.storage import Store
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import (
    AC_SETPOINT_KEEPALIVE_SECONDS,
    AC_SETPOINT_MIN_CHANGE,
    AC_SETPOINT_MIN_INTERVAL_SECONDS,
    ADAPTIVE_BIAS_DECAY,
    ADAPTIVE_BIAS_KI,
    CALIBRATION_MPC,
    CALIBRATION_OFFSET,
    CALIBRATION_TARGET,
    COMFORT_HUMIDITY_INFLUENCE_DEFAULT,
    CONF_ACS,
    CONF_CALIBRATION_HINTS,
    CONF_HOME_HUMIDITY_SENSOR,
    CONF_HOME_TEMP_SENSOR,
    CONF_OUTDOOR_SENSOR,
    CONF_TRVS,
    CONF_VALVE_HINTS,
    CONF_WEATHER_ENTITY,
    CONTROL_FAILURE_ISSUE_THRESHOLD,
    DEFAULT_PRESET,
    DEFAULT_PRESETS,
    DOMAIN,
    PRECONDITION_FORECAST_REFRESH_SECONDS,
    PRECONDITION_MAX_STEPS,
    RMOT_TAU_SECONDS,
    RUNTIME_WINDOW_SECONDS,
    SENSOR_MAX_AGE_DEFAULT,
    STARTUP_GRACE_SECONDS,
    UPDATE_INTERVAL_SECONDS,
    VALVE_MAINTENANCE_DWELL_SECONDS,
)
from .control.adaptive_bias import effective_bias, update_bias_integral
from .control.adaptive_comfort import (
    adaptive_band,
    running_mean_update,
)
from .control.comfort import effective_temperature
from .control.engine import (
    DeviceDecision,
    DeviceInput,
    DeviceKind,
    GlobalInput,
    decide,
)
from .control.forecast import expand_forecast
from .control.hysteresis import Demand
from .control.mpc.controller import MpcController, preconditioned_valve_pct
from .control.runtime_stats import cycles_per_hour, runtime_fraction
from .control.slope import temperature_slope_per_min
from .control.throttle import throttle_setpoint
from .control.window import window_suppresses
from .devices.adapter import ClimateAdapter
from .devices.command import build_command
from .devices.model import DeviceCommand, Mode
from .devices.trv import (
    LOCAL_CALIBRATION_HINTS,
    VALVE_OPENING_HINTS,
    find_related_number,
    local_offset,
)
from .models import (
    AcSetpoint,
    Band,
    DeviceReading,
    RuntimeSample,
    SmartClimateData,
    Status,
)
from .sensing.registry import build_snapshot
from .settings import (
    RuntimeSettings,
    area_band_offset,
    number_value,
    resolve_settings,
)
from .util import as_float, float_state

if TYPE_CHECKING:
    from collections.abc import Coroutine

_MPC_STORE_VERSION = 1


class _LearnedStateStore(Store[dict[str, Any]]):
    """Learned-state store with explicit schema-migration semantics.

    Everything persisted here is re-learnable in hours, so the migration
    policy is deliberately blunt: a payload whose schema we don't positively
    recognise is discarded rather than risk a mis-read. Same-major minor
    drift reads forward-compatibly (loaders validate field-by-field anyway).
    """

    async def _async_migrate_func(
        self,
        old_major_version: int,
        old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        if old_major_version == _MPC_STORE_VERSION:
            return old_data
        _LOGGER.warning(
            "climate_orchestrator: discarding persisted state with unknown"
            " schema v%s (current v%s); it will be re-learned",
            old_major_version,
            _MPC_STORE_VERSION,
        )
        return {}


# Skip number writes within this of the current value (update minimization).
NUMBER_WRITE_EPSILON = 0.1
_MPC_SAVE_DELAY = 30.0
# Learned state (MPC history, rmot EMA, bias integrals) moves slowly but
# *continuously*, so saving "on change" degenerates to saving every cycle —
# one flash write per ~90 s, forever, on SD-card Home Assistant boxes. Persist
# at most every this many seconds instead; a crash loses only that much slow
# drift (clean stops still flush pending saves via the Store itself).
_PERSIST_INTERVAL = 900.0

# Trailing window (seconds) and sample cap for the home temperature-slope figure.
_SLOPE_WINDOW_SECONDS = 900.0
_SLOPE_MAX_SAMPLES = 240
# Cap on cached hourly forecast entries. The longest look-ahead is 8 h; two
# days is already generous — a buggy weather entity must not grow the cache.
_FORECAST_MAX_HOURS = 48

_LOGGER = logging.getLogger(__name__)

type SmartClimateConfigEntry = ConfigEntry["SmartClimateCoordinator"]


@dataclass(slots=True)
class DeviceRuntime:
    """All mutable runtime state of one managed device, in one place.

    One instance per managed entity, created on first touch via
    ``SmartClimateCoordinator._runtime`` — so per-device init and cleanup are
    atomic instead of being scattered across parallel dicts.
    """

    demand: Demand = Demand.IDLE
    """Latched hysteresis demand (persisted across restarts)."""

    command: DeviceCommand | None = None
    """Last command actually sent (diagnostics sensors)."""

    ac_setpoint: AcSetpoint | None = None
    """Last written AC cooling setpoint, for write throttling."""

    run_samples: deque[RuntimeSample] = field(default_factory=deque)
    """Trailing (monotonic, running?) samples for the cycle/runtime counters."""

    mpc: MpcController | None = None
    """Learned MPC controller (TRVs in mpc calibration mode)."""

    valve: float | None = None
    """Last commanded valve fraction (0..1) in MPC mode."""

    ac_bias_integral: float = 0.0
    """Integral accumulator for the self-tuning AC setpoint bias."""

    command_failing: bool = False
    """Whether commands to this device are currently failing (log-once latch)."""


@dataclass(frozen=True, slots=True)
class CycleContext:
    """Everything one control cycle resolves once and shares across devices.

    Bundling these kills the 7-8 positional-argument signatures previously
    threaded through the per-device helpers (same-typed adjacent floats are
    exactly the swap-bug class neither mypy nor tests reliably catch).
    """

    settings: RuntimeSettings
    band: Band
    outdoor: float | None
    dt_min: float
    data: SmartClimateData


class SmartClimateCoordinator(DataUpdateCoordinator[SmartClimateData]):
    """Coordinate sensor resolution and (later) control for the whole home."""

    def __init__(self, hass: HomeAssistant, entry: SmartClimateConfigEntry) -> None:
        """Initialise the coordinator for a config entry."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=UPDATE_INTERVAL_SECONDS),
        )
        self.entry = entry
        self._unsub_state: CALLBACK_TYPE | None = None
        self._tracked: frozenset[str] = frozenset()
        # Post-restart warm-up bookkeeping: when we started, and whether we've
        # yet seen a usable home temperature. Drives the tri-state status so
        # transient startup gaps don't raise repairs (DESIGN.md §6.4).
        self._started = time.monotonic()
        self._ever_ready = False
        # Consecutive control-cycle failures (drives the repair issue).
        self._control_failures = 0
        # The last control cycle's resolved settings (see current_settings).
        self._cycle_settings: RuntimeSettings | None = None
        # Flash-wear rate limiting for the learned-state stores: when a save
        # was last scheduled, and the payloads it was scheduled with.
        self._last_persist: float | None = None
        self._mpc_scheduled: dict[str, Any] | None = None
        self._state_scheduled: dict[str, Any] | None = None
        # All mutable per-device state, one DeviceRuntime per managed entity.
        self._devices: dict[str, DeviceRuntime] = {}
        # The last cycle's decisions, replaced wholesale every control run (so
        # a removed device's decision doesn't linger in reasons/diagnostics).
        self.last_decisions: dict[str, DeviceDecision] = {}
        self._last_cycle: float | None = None
        # Per-area monotonic timestamp of when its window most recently opened,
        # plus a one-shot timer to re-run control when the grace delay expires.
        self._window_open_since: dict[str, float] = {}
        self._window_recheck_unsub: CALLBACK_TYPE | None = None
        # Trailing (time, home-avg-temp) samples and the latest slope (K/min).
        self._temp_samples: deque[tuple[float, float]] = deque(
            maxlen=_SLOPE_MAX_SAMPLES
        )
        self._temp_slope: float | None = None
        # Valve-maintenance bookkeeping (wall-clock epoch of the last run).
        self._maintenance_running = False
        self._last_maintenance: float | None = None
        # Adaptive comfort: running-mean outdoor temp and the shifted band.
        self._rmot: float | None = None
        self._adaptive_band: Band | None = None
        # Cached hourly outdoor forecast (°C, from the weather entity) for
        # forecast-based preconditioning, plus when it was last fetched.
        self._forecast_hourly: list[float] = []
        self._forecast_fetched_at = 0.0
        self._mpc_store: Store[dict[str, Any]] = _LearnedStateStore(
            hass, _MPC_STORE_VERSION, f"{DOMAIN}.{entry.entry_id}.mpc"
        )
        self._maint_store: Store[dict[str, Any]] = _LearnedStateStore(
            hass, _MPC_STORE_VERSION, f"{DOMAIN}.{entry.entry_id}.maintenance"
        )

    @callback
    def current_settings(self) -> RuntimeSettings:
        """Return the latest control cycle's resolved settings.

        Entities read this instead of re-resolving ~29 entity states per
        property access; settings changes re-run control immediately, which
        refreshes the snapshot.
        """
        if self._cycle_settings is None:
            self._cycle_settings = resolve_settings(self.hass, self.entry.entry_id)
        return self._cycle_settings

    @callback
    def _runtime(self, entity_id: str) -> DeviceRuntime:
        """Return the device's mutable runtime state, created on first touch."""
        return self._devices.setdefault(entity_id, DeviceRuntime())

    @callback
    def _background(self, coro: Coroutine[Any, Any, Any], name: str) -> None:
        """Run a fire-and-forget coroutine tied to the entry's lifecycle.

        Every spawned task goes through here so it is tracked by the config
        entry and cancelled on unload — a bare ``hass.async_create_task``
        could otherwise complete after shutdown (use-after-unload).
        """
        self.entry.async_create_background_task(
            self.hass, coro, name=f"{DOMAIN} {name}"
        )

    @staticmethod
    async def _load_store(
        store: Store[dict[str, Any]], label: str
    ) -> dict[str, Any] | None:
        """Load a learned-state store; a newer-schema payload never breaks setup.

        ``Store`` raises before our migrate hook when the stored *major*
        version exceeds the current one (downgrade scenario) — learned state
        is re-learnable, so discard it instead of failing the entry.
        """
        try:
            return await store.async_load()
        except UnsupportedStorageVersionError:
            _LOGGER.warning(
                "climate_orchestrator: persisted %s state was written by a"
                " newer release; discarding it (it will be re-learned)",
                label,
            )
            return None

    async def async_load_mpc(self) -> None:
        """Restore persisted MPC + maintenance state (call before first refresh).

        Only currently-managed entities are restored: the persist methods dump
        ``self._devices`` wholesale, so without this filter a device removed
        from the config would cycle store -> runtime -> store forever.
        """
        managed = set(self.device_ids)
        data = await self._load_store(self._mpc_store, "MPC")
        if data:
            for trv_id, payload in data.items():
                if trv_id not in managed:
                    _LOGGER.debug(
                        "climate_orchestrator: dropping persisted MPC state for"
                        " unmanaged %s",
                        trv_id,
                    )
                    continue
                try:
                    self._runtime(trv_id).mpc = MpcController.from_dict(payload)
                except (KeyError, TypeError, ValueError):
                    # A corrupt entry costs that TRV its learned state (it
                    # re-learns in hours) — never the whole integration setup.
                    _LOGGER.warning(
                        "climate_orchestrator: discarding corrupt MPC state for %s",
                        trv_id,
                    )
        maint = await self._load_store(self._maint_store, "maintenance")
        if maint:
            # isfinite: Python's json happily round-trips NaN/Infinity, so a
            # corrupted store could otherwise poison comparisons downstream.
            if isinstance(maint.get("last"), int | float) and math.isfinite(
                maint["last"]
            ):
                self._last_maintenance = float(maint["last"])
            if isinstance(maint.get("rmot"), int | float) and math.isfinite(
                maint["rmot"]
            ):
                self._rmot = float(maint["rmot"])
            if isinstance(integral := maint.get("ac_bias_integral"), dict):
                for k, v in integral.items():
                    if k in managed and isinstance(v, int | float) and math.isfinite(v):
                        self._runtime(k).ac_bias_integral = float(v)
            if isinstance(demand := maint.get("last_demand"), dict):
                valid = {d.value for d in Demand}
                for k, v in demand.items():
                    if k in managed and v in valid:
                        self._runtime(k).demand = Demand(v)

    @callback
    def _state_persist_data(self) -> dict[str, Any]:
        return {
            "last": self._last_maintenance,
            "rmot": self._rmot,
            "ac_bias_integral": {
                k: rt.ac_bias_integral for k, rt in self._devices.items()
            },
            "last_demand": {k: rt.demand.value for k, rt in self._devices.items()},
        }

    @callback
    def _mpc_persist_data(self) -> dict[str, Any]:
        return {
            trv_id: controller.to_dict()
            for trv_id, rt in self._devices.items()
            if (controller := rt.mpc) is not None
        }

    @callback
    def _maybe_persist(self) -> None:
        """Schedule learned-state saves, rate-limited for flash wear.

        Called every control cycle, but a store is only (delay-)saved when at
        least ``_PERSIST_INTERVAL`` has passed since the last scheduled save
        *and* its payload actually differs from what was last scheduled.
        """
        now = time.monotonic()
        if (
            self._last_persist is not None
            and now - self._last_persist < _PERSIST_INTERVAL
        ):
            return
        scheduled = False
        if (mpc := self._mpc_persist_data()) and mpc != self._mpc_scheduled:
            self._mpc_scheduled = mpc
            self._mpc_store.async_delay_save(self._mpc_persist_data, _MPC_SAVE_DELAY)
            scheduled = True
        if (state := self._state_persist_data()) != self._state_scheduled:
            self._state_scheduled = state
            self._maint_store.async_delay_save(
                self._state_persist_data, _MPC_SAVE_DELAY
            )
            scheduled = True
        if scheduled:
            self._last_persist = now

    @staticmethod
    async def async_remove_stores(hass: HomeAssistant, entry_id: str) -> None:
        """Delete the entry's persisted stores (called on entry removal)."""
        for suffix in ("mpc", "maintenance"):
            store: Store[dict[str, Any]] = Store(
                hass, _MPC_STORE_VERSION, f"{DOMAIN}.{entry_id}.{suffix}"
            )
            await store.async_remove()

    @property
    def _options(self) -> dict[str, object]:
        """Merged config: options override the original setup data."""
        return {**self.entry.data, **self.entry.options}

    def _id_list(self, key: str) -> list[str]:
        """Read a configured list of entity ids (defensively typed)."""
        value = self._options.get(key)
        return [str(item) for item in value] if isinstance(value, list) else []

    @property
    def trv_ids(self) -> list[str]:
        """Managed radiator-valve entities."""
        return self._id_list(CONF_TRVS)

    @property
    def ac_ids(self) -> list[str]:
        """Managed air-conditioner entities."""
        return self._id_list(CONF_ACS)

    @property
    def device_ids(self) -> list[str]:
        """All managed climate entities (TRVs followed by ACs)."""
        return [*self.trv_ids, *self.ac_ids]

    @property
    def outdoor_sensor(self) -> str | None:
        """The user-selected outdoor temperature sensor, if any."""
        value = self._options.get(CONF_OUTDOOR_SENSOR)
        return value if isinstance(value, str) else None

    @property
    def home_temp_sensor(self) -> str | None:
        """The user-provided whole-home average temperature sensor, if any."""
        value = self._options.get(CONF_HOME_TEMP_SENSOR)
        return value if isinstance(value, str) and value else None

    @property
    def home_humidity_sensor(self) -> str | None:
        """The user-provided whole-home average humidity sensor, if any."""
        value = self._options.get(CONF_HOME_HUMIDITY_SENSOR)
        return value if isinstance(value, str) and value else None

    @property
    def weather_entity(self) -> str | None:
        """The user-selected weather entity (forecast source), if any."""
        value = self._options.get(CONF_WEATHER_ENTITY)
        return value if isinstance(value, str) else None

    def _hint_tuple(self, key: str, default: tuple[str, ...]) -> tuple[str, ...]:
        """Parse a comma-separated hint string from options, else the default."""
        raw = self._options.get(key)
        if isinstance(raw, str):
            parts = tuple(h.strip().lower() for h in raw.split(",") if h.strip())
            if parts:
                return parts
        return default

    @property
    def valve_hints(self) -> tuple[str, ...]:
        """Name hints used to discover a TRV's valve-opening number entity."""
        return self._hint_tuple(CONF_VALVE_HINTS, VALVE_OPENING_HINTS)

    @property
    def calibration_hints(self) -> tuple[str, ...]:
        """Name hints used to discover a TRV's local-calibration number entity."""
        return self._hint_tuple(CONF_CALIBRATION_HINTS, LOCAL_CALIBRATION_HINTS)

    async def _async_update_data(self) -> SmartClimateData:
        """Resolve sensors and aggregates, keep listeners in sync, and actuate."""
        max_age_min = number_value(
            self.hass, self.entry.entry_id, "sensor_max_age", SENSOR_MAX_AGE_DEFAULT
        )
        data = build_snapshot(
            self.hass,
            self.device_ids,
            outdoor_sensor=self.outdoor_sensor,
            home_temp_sensor=self.home_temp_sensor,
            home_humidity_sensor=self.home_humidity_sensor,
            max_age_seconds=max_age_min * 60.0,
        )
        data = replace(data, status=self._compute_status(data))
        self._update_temp_slope(data.home_avg_temperature)
        self._ensure_subscription(data.tracked_entities)
        # Evict window timers for areas no longer backing any managed device
        # (a registry area change doesn't reload the entry, so without this
        # the dict would keep dead area keys for the coordinator's lifetime).
        live_areas = {
            r.area_id for r in data.readings.values() if r.area_id is not None
        }
        for area_id in list(self._window_open_since):
            if area_id not in live_areas:
                del self._window_open_since[area_id]
        # Actuation must never break the read-only snapshot/update — but a
        # *repeatedly* failing control loop must not stay silent in the log
        # either: count consecutive failures and raise a repair past the
        # threshold, cleared by the next clean cycle.
        try:
            await self._async_control(data)
        except Exception:
            self._control_failures += 1
            _LOGGER.exception(
                "climate_orchestrator: control cycle failed (%d consecutive)",
                self._control_failures,
            )
        else:
            self._control_failures = 0
        self._toggle_issue(
            "control_loop_failing",
            self._control_failures >= CONTROL_FAILURE_ISSUE_THRESHOLD,
            "control_loop_failing",
        )
        return data

    # --- Control / actuation -------------------------------------------------

    @callback
    def _desired(self) -> tuple[str, Band]:
        """Read the desired (hvac_mode, band) from the climate entity.

        The band's edges are the two setpoints; fall back to the active preset's
        edges (then the default preset) when the climate entity isn't ready.
        """
        entity_id = er.async_get(self.hass).async_get_entity_id(
            "climate", DOMAIN, self.entry.entry_id
        )
        state = self.hass.states.get(entity_id) if entity_id else None
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            default_low, default_high = DEFAULT_PRESETS[DEFAULT_PRESET]
            return HVACMode.OFF, Band(heat_edge=default_low, cool_edge=default_high)

        # Prefer the user-set *base* band (the climate entity may display the
        # adaptive-comfort-shifted cool edge in ``target_temp_high``; reading
        # that back would re-apply the shift each cycle).
        low = state.attributes.get(
            "base_target_temp_low", state.attributes.get("target_temp_low")
        )
        high = state.attributes.get(
            "base_target_temp_high", state.attributes.get("target_temp_high")
        )
        low_f, high_f = as_float(low), as_float(high)
        if low_f is None or high_f is None:
            # Missing *or* garbage attributes fall back to the preset band —
            # this read previously trusted float() blindly.
            preset = state.attributes.get("preset_mode", DEFAULT_PRESET)
            low_f, high_f = DEFAULT_PRESETS.get(preset, DEFAULT_PRESETS[DEFAULT_PRESET])
        return state.state, Band(heat_edge=low_f, cool_edge=high_f)

    @callback
    def _outdoor_temp(self) -> float | None:
        """Read the configured outdoor temperature sensor, if any."""
        return float_state(self.hass, self.outdoor_sensor)

    @callback
    def _update_temp_slope(self, home_temp: float | None) -> None:
        """Record the latest home-average temperature and recompute the slope."""
        if home_temp is None:
            return
        now = time.monotonic()
        self._temp_samples.append((now, home_temp))
        cutoff = now - _SLOPE_WINDOW_SECONDS
        while self._temp_samples and self._temp_samples[0][0] < cutoff:
            self._temp_samples.popleft()
        # (The sample-count cap is the deque's maxlen — enforced even when
        # this method isn't reached for a while.)
        self._temp_slope = temperature_slope_per_min(self._temp_samples)

    @property
    def temperature_slope(self) -> float | None:
        """Latest home-average temperature slope in K/min (diagnostic)."""
        return self._temp_slope

    @callback
    def mpc_state(self, trv_id: str) -> MpcController | None:
        """Return the MPC controller learned for a TRV, if any (diagnostics)."""
        runtime = self._devices.get(trv_id)
        return runtime.mpc if runtime else None

    @callback
    def mpc_diagnostics(self) -> dict[str, dict[str, float | int]]:
        """Learned MPC parameters per TRV (gain, loss, sample count)."""
        return {
            trv_id: {
                "gain": controller.params.gain,
                "loss": controller.params.loss,
                "samples": len(controller.history),
            }
            for trv_id, rt in self._devices.items()
            if (controller := rt.mpc) is not None
        }

    @callback
    def _cycle_minutes(self) -> float:
        """Minutes since the last control cycle (for MPC), with a sane default."""
        now = time.monotonic()
        if self._last_cycle is None:
            self._last_cycle = now
            return UPDATE_INTERVAL_SECONDS / 60.0
        elapsed = (now - self._last_cycle) / 60.0
        self._last_cycle = now
        return elapsed if elapsed > 0 else UPDATE_INTERVAL_SECONDS / 60.0

    @callback
    def _window_open(self, reading: DeviceReading, delay_seconds: float) -> bool:
        """Debounced window-open for a device: open only after the grace delay.

        Tracks when each area's window first opened and suppresses heating/
        cooling once it has stayed open for ``delay_seconds``. Schedules a
        one-shot refresh so control re-runs exactly when the delay elapses
        (rather than waiting for the next keepalive).
        """
        raw_open = reading.window_open
        area_id = reading.area_id
        if not raw_open:
            if area_id is not None:
                self._window_open_since.pop(area_id, None)
            return False
        if area_id is None:
            # No area key to debounce against; honour the delay only as on/off.
            return delay_seconds <= 0.0

        now = time.monotonic()
        opened_at = self._window_open_since.get(area_id)
        if opened_at is None:
            self._window_open_since[area_id] = opened_at = now
            if delay_seconds > 0.0:
                self._schedule_window_recheck(delay_seconds)
        return window_suppresses(raw_open, opened_at, now, delay_seconds)

    @callback
    def _schedule_window_recheck(self, delay_seconds: float) -> None:
        """Re-run control shortly after a window's grace delay expires."""
        if self._window_recheck_unsub is not None:
            self._window_recheck_unsub()

        @callback
        def _fire(_now: object) -> None:
            self._window_recheck_unsub = None
            self._background(self.async_request_refresh(), "window recheck refresh")

        # A small margin ensures the elapsed check passes when it fires.
        self._window_recheck_unsub = async_call_later(
            self.hass, delay_seconds + 0.5, _fire
        )

    async def _write_number_if_changed(self, entity_id: str, value: float) -> None:
        """Write a number entity, skipping no-op changes (update minimization)."""
        current = float_state(self.hass, entity_id)
        if current is not None and abs(current - value) < NUMBER_WRITE_EPSILON:
            return
        await self.hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_id, "value": value},
            blocking=True,
        )

    def _calibration_writes(
        self,
        entity_id: str,
        decision: DeviceDecision,
        reading: DeviceReading,
        ctx: CycleContext,
        adapter: ClimateAdapter,
    ) -> list[Coroutine[Any, Any, None]]:
        """Extra MPC/offset writes for a TRV (dispatch by calibration mode).

        While heating, MPC drives the valve opening and offset mode corrects
        the local calibration. When *not* heating in MPC mode the valve is
        driven fully shut — otherwise it would linger at its last commanded
        opening (a common cause of a TRV that "stays open" and keeps heating).
        """
        if decision.demand is not Demand.HEAT:
            return self._idle_valve_writes(entity_id, ctx)
        if ctx.settings.calibration_mode == CALIBRATION_MPC:
            return self._mpc_valve_writes(entity_id, reading.area_temperature, ctx)
        if ctx.settings.calibration_mode == CALIBRATION_OFFSET:
            return self._offset_writes(entity_id, reading.area_temperature, adapter)
        return []

    def _idle_valve_writes(
        self, entity_id: str, ctx: CycleContext
    ) -> list[Coroutine[Any, Any, None]]:
        """Drive an MPC TRV's valve fully shut while it isn't heating."""
        if ctx.settings.calibration_mode != CALIBRATION_MPC:
            return []
        number = find_related_number(self.hass, entity_id, self.valve_hints)
        if number is None:
            return []
        self._runtime(entity_id).valve = 0.0
        return [self._write_number_if_changed(number, 0.0)]

    def _mpc_valve_writes(
        self, entity_id: str, area_temp: float | None, ctx: CycleContext
    ) -> list[Coroutine[Any, Any, None]]:
        """Observe the room, optimise the valve opening, and write it."""
        number = find_related_number(self.hass, entity_id, self.valve_hints)
        self._calibration_issue(entity_id, "mpc", missing=number is None)
        if number is None or area_temp is None:
            return []
        return [self._mpc_observe_and_write(entity_id, number, area_temp, ctx)]

    async def _mpc_observe_and_write(
        self, entity_id: str, number: str, area_temp: float, ctx: CycleContext
    ) -> None:
        """Run the MPC math in the executor, then write the valve opening.

        scipy (system identification + optimisation) is synchronous; running
        it in an executor job keeps the event loop unblocked. Each TRV has its
        own controller, so concurrent jobs never share state.
        """
        ambient = ctx.outdoor if ctx.outdoor is not None else area_temp
        runtime = self._runtime(entity_id)
        if runtime.mpc is None:
            runtime.mpc = MpcController()
        controller = runtime.mpc
        last_valve = 0.0 if runtime.valve is None else runtime.valve
        series = self._precondition_series(ctx.dt_min, ctx.settings)

        def _observe_and_optimize() -> float:
            controller.observe(
                temp=area_temp, valve=last_valve, outdoor=ambient, dt=ctx.dt_min
            )
            # Plan from the Kalman-filtered estimate (smooths sensor noise);
            # raw reading as a guard, though observe() always seeds one.
            estimate = controller.estimated_temperature
            return preconditioned_valve_pct(
                controller,
                temp=area_temp if estimate is None else estimate,
                target=ctx.band.heat_target(ctx.settings.tolerance),
                outdoor=ambient,
                series=series,
                dt=ctx.dt_min,
            )

        pct = await self.hass.async_add_executor_job(_observe_and_optimize)
        runtime.valve = pct / 100.0
        await self._write_number_if_changed(number, pct)

    def _offset_writes(
        self, entity_id: str, area_temp: float | None, adapter: ClimateAdapter
    ) -> list[Coroutine[Any, Any, None]]:
        """Write the local-calibration offset so the TRV sees the area temp."""
        number = find_related_number(self.hass, entity_id, self.calibration_hints)
        self._calibration_issue(entity_id, "offset", missing=number is None)
        offset = local_offset(area_temp, adapter.read().current_temp)
        if number is None or offset is None:
            return []
        return [self._write_number_if_changed(number, offset)]

    @callback
    def _compute_status(self, data: SmartClimateData) -> Status:
        """Classify the orchestrator as initializing / ok / degraded.

        With nothing managed there's nothing to warm up (``OK``). Once a usable
        home temperature is ever seen the warm-up is over for good: ``OK``, or
        ``DEGRADED`` if a managed device is unavailable. Before that first
        reading we're ``INITIALIZING`` until the grace window elapses — after
        which a persistent lack of any reading is a real fault (``DEGRADED``).
        """
        if not self.device_ids:
            return Status.OK
        if data.home_avg_temperature is not None:
            self._ever_ready = True
        if self._ever_ready:
            return Status.DEGRADED if data.unavailable_devices else Status.OK
        if time.monotonic() - self._started < STARTUP_GRACE_SECONDS:
            return Status.INITIALIZING
        return Status.DEGRADED

    @callback
    def _calibration_issue(self, entity_id: str, mode: str, *, missing: bool) -> None:
        """Raise/clear a repair issue when a TRV lacks its calibration number."""
        issue_id = f"missing_calibration_number_{entity_id}"
        if missing:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key="missing_calibration_number",
                translation_placeholders={"entity_id": entity_id, "mode": mode},
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    @callback
    def _toggle_issue(self, issue_id: str, active: bool, key: str) -> None:
        """Create or clear a static (no-placeholder) repair issue."""
        if active:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                issue_id,
                is_fixable=False,
                severity=ir.IssueSeverity.WARNING,
                translation_key=key,
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    @callback
    def _environment_issues(
        self, settings: RuntimeSettings, data: SmartClimateData, base_band: Band
    ) -> None:
        """Surface misconfigurations that would otherwise fail silently."""
        # An inverted band (cool edge below heat edge) has no neutral zone, so
        # the home would heat below the cool edge and cool above it — running
        # constantly. Flag it rather than burn energy silently.
        self._toggle_issue(
            "inverted_band",
            base_band.cool_edge < base_band.heat_edge,
            "inverted_band",
        )
        # Adaptive comfort is opt-in, so enabling it without an outdoor sensor is
        # a clear mistake. Outdoor gating is on by default, so don't nag about it.
        self._toggle_issue(
            "outdoor_sensor_missing",
            settings.adaptive_cooling_comfort and self.outdoor_sensor is None,
            "outdoor_sensor_missing",
        )
        # Forecast preconditioning needs a weather entity to read a forecast from.
        self._toggle_issue(
            "weather_forecast_missing",
            settings.forecast_preconditioning and self.weather_entity is None,
            "weather_forecast_missing",
        )
        # These two are transient right after a restart (sensors haven't
        # reported in yet), so hold them back while still initializing — only
        # raise once warm-up is over and the gap is therefore real.
        settled = not data.initializing
        self._toggle_issue(
            "no_temperature_source",
            settled and bool(self.device_ids) and data.home_avg_temperature is None,
            "no_temperature_source",
        )
        self._toggle_issue(
            "stale_sensor",
            settled and bool(data.stale_sensors),
            "stale_sensor",
        )

    @callback
    def _room_effective(
        self, reading: DeviceReading, ctx: CycleContext
    ) -> float | None:
        """Return the device's comfort-adjusted room temperature (area, else home)."""
        comfort = ctx.settings.comfort_index_targeting
        influence = ctx.settings.comfort_humidity_influence
        area_temp = reading.area_temperature
        if area_temp is not None:
            humidity = reading.area_humidity
            return effective_temperature(
                area_temp, humidity, use_comfort=comfort, influence=influence
            )
        if ctx.data.home_avg_temperature is not None:
            return effective_temperature(
                ctx.data.home_avg_temperature,
                ctx.data.home_avg_humidity,
                use_comfort=comfort,
                influence=influence,
            )
        return None

    @callback
    def _apply_adaptive_comfort(
        self,
        base_band: Band,
        outdoor: float | None,
        settings: RuntimeSettings,
        dt_min: float,
    ) -> Band:
        """Update the running-mean outdoor temp and return the band to control on.

        Adaptive comfort only relaxes *cooling* in the heat: once the
        running-mean outdoor temperature climbs past the cool edge (plus the
        onset bias), the cool setpoint drifts up by a smooth, saturating amount
        capped at ``max_shift``. The heat edge is never touched, so a device is
        never made to work harder than the user's preset. The shifted band is
        always computed for the preview sensors; it's only *applied* when the
        toggle is on.
        """
        self._rmot = running_mean_update(
            self._rmot, outdoor, dt_seconds=dt_min * 60.0, tau_seconds=RMOT_TAU_SECONDS
        )
        heat_edge, cool_edge = adaptive_band(
            base_band.heat_edge,
            base_band.cool_edge,
            self._rmot,
            settings.adaptive_cooling_comfort_max_shift,
            bias=settings.adaptive_cooling_comfort_onset_bias,
            response=settings.adaptive_cooling_comfort_response,
        )
        self._adaptive_band = Band(heat_edge=heat_edge, cool_edge=cool_edge)
        return self._adaptive_band if settings.adaptive_cooling_comfort else base_band

    async def _refresh_forecast(self, settings: RuntimeSettings) -> None:
        """Fetch and cache the weather entity's hourly outdoor forecast.

        Only when preconditioning is enabled and a weather entity is configured;
        rate-limited to ``PRECONDITION_FORECAST_REFRESH_SECONDS``. Failures are
        swallowed (the feature simply no-ops without a forecast).
        """
        if not settings.forecast_preconditioning or self.weather_entity is None:
            self._forecast_hourly = []
            return
        now = time.monotonic()
        if (
            self._forecast_hourly
            and now - self._forecast_fetched_at < PRECONDITION_FORECAST_REFRESH_SECONDS
        ):
            return
        try:
            response = await self.hass.services.async_call(
                "weather",
                "get_forecasts",
                {"entity_id": self.weather_entity, "type": "hourly"},
                blocking=True,
                return_response=True,
            )
        except Exception:
            _LOGGER.debug("climate_orchestrator: forecast fetch failed", exc_info=True)
            return
        # The service response is loosely typed JSON; narrow every step.
        if not isinstance(response, dict):
            return
        device_block = response.get(self.weather_entity)
        if not isinstance(device_block, dict):
            return
        entries = device_block.get("forecast")
        if not isinstance(entries, list):
            return
        temps: list[float] = []
        for entry in entries:
            if isinstance(entry, dict):
                temp = entry.get("temperature")
                if (
                    isinstance(temp, int | float)
                    and not isinstance(temp, bool)
                    and math.isfinite(temp)
                ):
                    temps.append(float(temp))
        if temps:
            self._forecast_hourly = temps[:_FORECAST_MAX_HOURS]
            self._forecast_fetched_at = now

    @callback
    def _precondition_series(
        self, dt_min: float, settings: RuntimeSettings
    ) -> list[float] | None:
        """Per-step outdoor forecast series for the valve optimiser, or ``None``.

        Interpolates the cached hourly forecast onto the control step over the
        preconditioning look-ahead; ``None`` when the feature is off or there's
        no forecast yet.
        """
        if not settings.forecast_preconditioning or not self._forecast_hourly:
            return None
        steps = round(settings.preconditioning_horizon * 60.0 / dt_min)
        steps = max(1, min(steps, PRECONDITION_MAX_STEPS))
        series = expand_forecast(self._forecast_hourly, dt_min, steps)
        return series or None

    @property
    def comfort_influence(self) -> float:
        """The comfort-index humidity influence factor (live)."""
        return number_value(
            self.hass,
            self.entry.entry_id,
            "comfort_humidity_influence",
            COMFORT_HUMIDITY_INFLUENCE_DEFAULT,
        )

    @property
    def running_mean_outdoor(self) -> float | None:
        """Running-mean outdoor temperature driving adaptive comfort (°C)."""
        return self._rmot

    @property
    def adaptive_band_high(self) -> float | None:
        """Would-be cool edge after the adaptive-comfort shift (preview).

        Only the cool edge is ever relaxed; the heat edge is never touched, so
        there is no matching "low" accessor.
        """
        return self._adaptive_band.cool_edge if self._adaptive_band else None

    @callback
    def hvac_action_reason(self) -> str:
        """Return a single headline reason for the current heat/cool/idle state."""
        hvac_mode, _ = self._desired()
        if hvac_mode == HVACMode.OFF:
            return "off"
        decisions = list(self.last_decisions.values())
        if not decisions:
            return "idle"
        reasons = {d.reason for d in decisions}
        if any(d.demand is Demand.HEAT for d in decisions):
            return "frost_protection" if "frost_protection" in reasons else "heating"
        if any(d.demand is Demand.COOL for d in decisions):
            return "cooling"
        if any(d.dry_mode for d in decisions):
            return "dehumidifying"
        for reason in ("window_open", "outdoor_gating", "unavailable", "no_data"):
            if reason in reasons:
                return reason
        return "idle"

    @callback
    def device_reasons(self) -> dict[str, str]:
        """Per-device decision reasons, for the reason sensor's attributes."""
        return {key: d.reason for key, d in self.last_decisions.items()}

    # --- Per-device diagnostics / counters ----------------------------------

    @callback
    def _record_runtime(self, decisions: dict[str, DeviceDecision]) -> None:
        """Append a (monotonic, running?) sample per device, pruned to the window."""
        now = time.monotonic()
        cutoff = now - RUNTIME_WINDOW_SECONDS
        for entity_id, decision in decisions.items():
            running = decision.demand in (Demand.HEAT, Demand.COOL)
            samples = self._runtime(entity_id).run_samples
            samples.append(RuntimeSample(at=now, running=running))
            # Keep one sample before the cutoff so the integral spans the edge.
            while len(samples) > 1 and samples[1].at < cutoff:
                samples.popleft()

    @callback
    def device_action(self, entity_id: str) -> str:
        """Per-device action label (idle/heating/cooling/drying/off/unavailable)."""
        decision = self.last_decisions.get(entity_id)
        if decision is None:
            return "idle"
        if decision.reason == "unavailable":
            return "unavailable"
        if decision.reason == "master_off":
            return "off"
        if decision.demand is Demand.HEAT:
            return "heating"
        if decision.demand is Demand.COOL:
            return "cooling"
        if decision.dry_mode:
            return "drying"
        return "idle"

    @callback
    def device_command_attrs(self, entity_id: str) -> dict[str, str | float | None]:
        """Return the last command sent to a device (mode + setpoint)."""
        runtime = self._devices.get(entity_id)
        command = runtime.command if runtime else None
        if command is None:
            return {}
        return {
            "commanded_mode": command.hvac_mode.value,
            "commanded_setpoint": command.target_temp,
        }

    @callback
    def valve_position(self, entity_id: str) -> float | None:
        """Last commanded valve opening (%) for a TRV in MPC mode, else None."""
        runtime = self._devices.get(entity_id)
        valve = runtime.valve if runtime else None
        return None if valve is None else round(valve * 100.0, 1)

    @callback
    def device_runtime_fraction(self, entity_id: str) -> float | None:
        """Fraction of the trailing window the device was running (0..1)."""
        runtime = self._devices.get(entity_id)
        if runtime is None:
            return None
        return runtime_fraction(
            list(runtime.run_samples), time.monotonic(), RUNTIME_WINDOW_SECONDS
        )

    @callback
    def device_cycles_per_hour(self, entity_id: str) -> float | None:
        """Off->on starts per hour over the trailing window."""
        runtime = self._devices.get(entity_id)
        if runtime is None:
            return None
        return cycles_per_hour(
            list(runtime.run_samples), time.monotonic(), RUNTIME_WINDOW_SECONDS
        )

    @callback
    def frost_active(self) -> bool:
        """Whether any device is currently in forced frost-protection heating."""
        return any(d.reason == "frost_protection" for d in self.last_decisions.values())

    @callback
    def dew_point_active(self) -> bool:
        """Whether any AC is currently running dry mode for the dew-point guard."""
        return any(d.dry_mode for d in self.last_decisions.values())

    @callback
    def _ac_bias(
        self,
        entity_id: str,
        kind: DeviceKind,
        decision: DeviceDecision,
        reading: DeviceReading,
        ctx: CycleContext,
    ) -> float:
        """Effective AC setpoint bias, adapted by integral feedback if enabled.

        Heaters always use the plain base bias (it's ignored for them anyway).
        For an AC, the bias used *this* cycle reflects the accumulated integral;
        the accumulator is then advanced for next cycle from the current error.
        """
        settings = ctx.settings
        base = settings.ac_setpoint_bias
        if kind is not DeviceKind.COOLER or not settings.self_tuning_ac_bias:
            return base

        runtime = self._runtime(entity_id)
        integral = runtime.ac_bias_integral
        max_add = max(0.0, settings.ac_setpoint_bias_max - base)
        bias = effective_bias(base, integral, settings.ac_setpoint_bias_max)

        room = reading.area_temperature
        if room is None:
            # Fall back to *this* cycle's home average (ctx.data), not the
            # previously published self.data — the integral error should be
            # computed against the readings the rest of the cycle acts on.
            room = ctx.data.home_avg_temperature
        if room is not None:
            runtime.ac_bias_integral = update_bias_integral(
                integral,
                error=room - ctx.band.cool_target(settings.tolerance),
                dt_min=ctx.dt_min,
                ki=ADAPTIVE_BIAS_KI,
                max_add=max_add,
                cooling=decision.demand is Demand.COOL,
                decay=ADAPTIVE_BIAS_DECAY,
            )
        return bias

    @callback
    def _throttle_ac_setpoint(
        self, entity_id: str, command: DeviceCommand
    ) -> DeviceCommand:
        """Hold an AC's cooling setpoint between cycles to avoid write spam.

        Non-cooling commands pass through and reset the throttle (so the next
        cooling run writes fresh). A cooling command may have its setpoint
        replaced with the previously written value per ``throttle_setpoint``.
        """
        runtime = self._runtime(entity_id)
        if command.hvac_mode is not Mode.COOL or command.target_temp is None:
            runtime.ac_setpoint = None
            return command
        prev = runtime.ac_setpoint
        value, ts = throttle_setpoint(
            prev.value if prev else None,
            prev.written_at if prev else None,
            command.target_temp,
            time.monotonic(),
            min_change=AC_SETPOINT_MIN_CHANGE,
            min_interval_s=AC_SETPOINT_MIN_INTERVAL_SECONDS,
            keepalive_s=AC_SETPOINT_KEEPALIVE_SECONDS,
        )
        runtime.ac_setpoint = AcSetpoint(value=value, written_at=ts)
        if value != command.target_temp:
            return replace(command, target_temp=value)
        return command

    def _control_one(
        self,
        entity_id: str,
        kind: DeviceKind,
        reading: DeviceReading,
        global_input: GlobalInput,
        *,
        window_open: bool,
        other_window_open: bool,
        ctx: CycleContext,
    ) -> tuple[DeviceDecision, list[tuple[str, Coroutine[Any, Any, None]]]]:
        """Decide one device and build its ``(entity_id, write)`` pairs.

        Updates the device's runtime latch/last-command as a side effect.
        Returning the writes *paired* with the entity id (instead of appending
        to two parallel lists) keeps the failure-logging zip structurally
        impossible to desynchronize when calibration adds extra writes.
        """
        runtime = self._runtime(entity_id)
        decision = decide(
            DeviceInput(
                key=entity_id,
                kind=kind,
                available=reading.available,
                local_temp=reading.area_temperature,
                local_humidity=reading.area_humidity,
                window_open=window_open,
                other_window_open=other_window_open,
                previous=runtime.demand,
                offset=area_band_offset(
                    self.hass, self.entry.entry_id, reading.area_id
                ),
            ),
            global_input,
        )
        runtime.demand = decision.demand
        if not reading.available:
            return decision, []  # excluded this cycle, but its latch is preserved
        adapter = ClimateAdapter(self.hass, entity_id)
        command = build_command(
            decision,
            kind,
            band=ctx.band,
            ac_setpoint_bias=self._ac_bias(entity_id, kind, decision, reading, ctx),
            caps=adapter.capabilities(),
            tolerance=ctx.settings.tolerance,
            device_current_temp=adapter.read().current_temp,
            room_temp=self._room_effective(reading, ctx),
        )
        command = self._throttle_ac_setpoint(entity_id, command)
        runtime.command = command
        writes: list[tuple[str, Coroutine[Any, Any, None]]] = [
            (entity_id, adapter.apply(command))
        ]
        if (
            kind is DeviceKind.HEATER
            and ctx.settings.calibration_mode != CALIBRATION_TARGET
        ):
            writes += [
                (entity_id, coro)
                for coro in self._calibration_writes(
                    entity_id, decision, reading, ctx, adapter
                )
            ]
        return decision, writes

    async def _async_control(self, data: SmartClimateData) -> None:
        """Decide per device, apply commands, and run TRV calibration."""
        settings = self._cycle_settings = resolve_settings(
            self.hass, self.entry.entry_id
        )
        await self._refresh_forecast(settings)
        dt_min = self._cycle_minutes()
        hvac_mode, base_band = self._desired()
        outdoor = self._outdoor_temp()
        band = self._apply_adaptive_comfort(base_band, outdoor, settings, dt_min)
        self._environment_issues(settings, data, base_band)
        global_input = GlobalInput(
            band=band,
            release_offset=settings.release_offset,
            tolerance=settings.tolerance,
            home_temp=data.home_avg_temperature,
            home_humidity=data.home_avg_humidity,
            home_trigger=settings.home_average_trigger,
            outdoor_temp=outdoor,
            master_off=hvac_mode == HVACMode.OFF,
            use_comfort=settings.comfort_index_targeting,
            comfort_influence=settings.comfort_humidity_influence,
            dew_point_threshold=(
                settings.dew_point_threshold if settings.dew_point_guard else None
            ),
            frost_temp=settings.frost_protection_temp,
            heat_off_outdoor=settings.heat_off_outdoor,
            cool_off_outdoor=settings.cool_off_outdoor,
            window_detection=settings.window_open_detection,
            ac_ignore_window=settings.ac_ignore_window,
            frost_protection=settings.frost_protection,
            outdoor_gating=settings.outdoor_temp_gating and outdoor is not None,
            ac_heating_assist=settings.ac_heating_assist,
        )

        ctx = CycleContext(
            settings=settings, band=band, outdoor=outdoor, dt_min=dt_min, data=data
        )
        trvs = set(self.trv_ids)
        # Debounced window-open per device, plus the set of areas with a window
        # open — so a cooler exempted via `ac_ignore_window` can ignore its own
        # area's window yet still be suppressed by a window open in another room.
        delay_s = settings.window_open_delay * 60.0
        window_state = {
            eid: self._window_open(reading, delay_s)
            for eid in self.device_ids
            if (reading := data.readings.get(eid)) is not None
        }
        # Area-less devices can't open a window for "another room": filter the
        # None area explicitly (today window_open is only ever set per-area,
        # but that invariant lives three files away — make it local).
        open_areas = {
            area_id
            for eid, opened in window_state.items()
            if opened and (area_id := data.readings[eid].area_id) is not None
        }
        decisions: dict[str, DeviceDecision] = {}
        writes: list[tuple[str, Coroutine[Any, Any, None]]] = []
        for entity_id in self.device_ids:
            reading = data.readings.get(entity_id)
            if reading is None:
                continue
            decision, device_writes = self._control_one(
                entity_id,
                DeviceKind.HEATER if entity_id in trvs else DeviceKind.COOLER,
                reading,
                global_input,
                window_open=window_state.get(entity_id, False),
                other_window_open=any(a != reading.area_id for a in open_areas),
                ctx=ctx,
            )
            decisions[entity_id] = decision
            writes.extend(device_writes)

        self.last_decisions = decisions
        self._record_runtime(decisions)
        if writes:
            results = await asyncio.gather(
                *(coro for _, coro in writes), return_exceptions=True
            )
            failures: dict[str, Exception] = {}
            for (entity_id, _), result in zip(writes, results, strict=True):
                if isinstance(result, Exception):
                    failures.setdefault(entity_id, result)
            # Log once per outage, not once per cycle: a device that stays
            # down would otherwise emit a warning every UPDATE_INTERVAL.
            for entity_id in {eid for eid, _ in writes}:
                runtime = self._runtime(entity_id)
                if (error := failures.get(entity_id)) is not None:
                    if not runtime.command_failing:
                        runtime.command_failing = True
                        _LOGGER.warning(
                            "climate_orchestrator: failed to command %s: %s "
                            "(suppressing repeats until it recovers)",
                            entity_id,
                            error,
                        )
                elif runtime.command_failing:
                    runtime.command_failing = False
                    _LOGGER.info(
                        "climate_orchestrator: %s is accepting commands again",
                        entity_id,
                    )
        self._maybe_persist()
        self._maybe_auto_maintenance(settings, decisions)

    @callback
    def _ensure_subscription(self, tracked: frozenset[str]) -> None:
        """(Re)subscribe to state changes when the tracked set changes."""
        if tracked == self._tracked and self._unsub_state is not None:
            return
        if self._unsub_state is not None:
            self._unsub_state()
            self._unsub_state = None
        self._tracked = tracked
        if tracked:
            self._unsub_state = async_track_state_change_event(
                self.hass, list(tracked), self._handle_state_event
            )

    @callback
    def _handle_state_event(self, event: Event[EventStateChangedData]) -> None:
        """Trigger a (debounced) refresh when a tracked entity changes."""
        self._background(self.async_request_refresh(), "state-change refresh")

    # --- Services / maintenance ---------------------------------------------

    async def async_reset_mpc(self, trv_ids: list[str] | None = None) -> None:
        """Forget learned MPC state for some/all TRVs and re-run control."""
        targets = trv_ids or self.trv_ids
        for trv_id in targets:
            if (runtime := self._devices.get(trv_id)) is not None:
                runtime.mpc = None
                runtime.valve = None
        await self._mpc_store.async_save(self._mpc_persist_data())
        await self.async_request_refresh()

    async def _write_number(self, entity_id: str, value: float) -> None:
        """Write a number entity unconditionally (no no-op skipping).

        Valve maintenance must exercise the full travel even if the number
        already reads the target — hence no epsilon check here.
        """
        await self.hass.services.async_call(
            "number",
            "set_value",
            {"entity_id": entity_id, "value": value},
            blocking=True,
        )

    async def async_run_valve_maintenance(
        self,
        trv_ids: list[str] | None = None,
        *,
        dwell: float = VALVE_MAINTENANCE_DWELL_SECONDS,
    ) -> bool:
        """Exercise each TRV's valve fully open then closed, then restore control.

        Prevents the valve seizing/scaling when it sits at a fixed opening for a
        long time. Re-entrancy guarded so overlapping triggers can't stack.
        Returns whether any valve numbers were found — the service layer turns
        ``False`` into a translated ``ServiceValidationError``.
        """
        valves = [
            number
            for trv_id in (trv_ids or self.trv_ids)
            if (number := find_related_number(self.hass, trv_id, VALVE_OPENING_HINTS))
        ]
        if not valves:
            return False
        if self._maintenance_running:
            return True
        self._maintenance_running = True
        try:
            for opening in (100.0, 0.0):
                await asyncio.gather(
                    *(self._write_number(number, opening) for number in valves),
                    return_exceptions=True,
                )
                await asyncio.sleep(dwell)
            self._last_maintenance = time.time()
            await self._maint_store.async_save(self._state_persist_data())
        finally:
            self._maintenance_running = False
            # Restore normal valve positions on the next cycle.
            await self.async_request_refresh()
        return True

    @callback
    def _maybe_auto_maintenance(
        self, settings: RuntimeSettings, decisions: dict[str, DeviceDecision]
    ) -> None:
        """Kick off auto valve maintenance when due and the home isn't heating."""
        if not settings.auto_valve_maintenance or self._maintenance_running:
            return
        now = time.time()
        if self._last_maintenance is None:
            # First run after install: start the clock rather than acting now.
            self._last_maintenance = now
            self._background(
                self._maint_store.async_save(self._state_persist_data()),
                "maintenance clock save",
            )
            return
        if now - self._last_maintenance < settings.valve_maintenance_interval * 86400:
            return
        trvs = set(self.trv_ids)
        if any(d.demand is Demand.HEAT for key, d in decisions.items() if key in trvs):
            return  # don't interrupt active heating
        self._background(self.async_run_valve_maintenance(), "auto valve maintenance")

    async def async_shutdown(self) -> None:
        """Cancel listeners, flush MPC state, and shut the coordinator down."""
        if self._unsub_state is not None:
            self._unsub_state()
            self._unsub_state = None
        if self._window_recheck_unsub is not None:
            self._window_recheck_unsub()
            self._window_recheck_unsub = None
        if any(rt.mpc is not None for rt in self._devices.values()):
            await self._mpc_store.async_save(self._mpc_persist_data())
        # The rate limiter may be holding back up to _PERSIST_INTERVAL of
        # slow-moving state — flush it now that we're going away for real.
        await self._maint_store.async_save(self._state_persist_data())
        await super().async_shutdown()
