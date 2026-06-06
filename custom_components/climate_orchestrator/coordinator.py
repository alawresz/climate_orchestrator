"""Coordinator for the Climate Orchestrator integration.

Owns the shared runtime snapshot and the control cycle: each cycle resolves
the area sensors into a snapshot, decides every managed device through the
control engine, and applies the minimal writes. It is event-driven
(state-change listeners over the managed devices and their area sensors) with
a periodic keepalive, and re-subscribes when the tracked set changes.
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
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.helpers.event import (
    async_track_state_change_event,
)
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .adaptation import WeatherAdaptation
from .const import (
    AC_SETPOINT_KEEPALIVE_SECONDS,
    AC_SETPOINT_MIN_CHANGE,
    AC_SETPOINT_MIN_INTERVAL_SECONDS,
    ADAPTIVE_BIAS_DECAY,
    ADAPTIVE_BIAS_KI,
    CALIBRATION_MPC,
    CALIBRATION_OFFSET,
    CALIBRATION_TARGET,
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
    MPC_POOR_FIT_RATIO,
    MPC_POOR_FIT_SECONDS,
    RUNTIME_WINDOW_SECONDS,
    STARTUP_GRACE_SECONDS,
    UPDATE_INTERVAL_SECONDS,
    VALVE_MAINTENANCE_DWELL_SECONDS,
)
from .control.adaptive_bias import effective_bias, update_bias_integral
from .control.comfort import effective_temperature
from .control.engine import (
    DeviceDecision,
    DeviceInput,
    DeviceKind,
    GlobalInput,
    decide,
)
from .control.hysteresis import Demand
from .control.mpc.controller import MpcController, preconditioned_valve_pct
from .control.runtime_stats import cycles_per_hour, runtime_fraction
from .control.slope import temperature_slope_per_min
from .control.throttle import throttle_setpoint
from .devices.adapter import ClimateAdapter
from .devices.command import build_command
from .devices.model import DeviceCommand, Mode
from .devices.profiles import profile_for_entity
from .devices.trv import (
    LOCAL_CALIBRATION_HINTS,
    VALVE_OPENING_HINTS,
    find_related_number,
    local_offset,
)
from .events import EventBridge
from .models import (
    AcSetpoint,
    Band,
    DeviceReading,
    RuntimeSample,
    SmartClimateData,
    Status,
)
from .persistence import LearnedStateStores
from .repairs import (
    calibration_issue,
    capability_issues,
    command_ignored_issue,
    environment_issues,
    mpc_poor_fit_issue,
    toggle_issue,
)
from .sensing.registry import build_snapshot
from .settings import (
    RuntimeSettings,
    area_band_offset,
    clamped_number_value,
    enabled_presets,
    resolve_settings,
)
from .supervision import DeviceSupervisor
from .util import as_float, float_state
from .windows import WindowMonitor

if TYPE_CHECKING:
    from collections.abc import Coroutine

# Skip number writes within this of the current value (update minimization).
NUMBER_WRITE_EPSILON = 0.1
# Trailing window (seconds) and sample cap for the home temperature-slope figure.
_SLOPE_WINDOW_SECONDS = 900.0
_SLOPE_MAX_SAMPLES = 240
_LOGGER = logging.getLogger(__name__)

type SmartClimateConfigEntry = ConfigEntry["SmartClimateCoordinator"]


@dataclass(slots=True)
class DeviceRuntime:
    """All mutable runtime state of one managed device, in one place.

    One instance per managed entity, created on first touch via
    ``SmartClimateCoordinator._runtime`` — one object per device keeps init
    and cleanup atomic (no parallel per-field dicts to keep in sync).
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

    ignored_mode: str | None = None
    """Commanded HVAC mode of the current non-compliance streak (watchdog)."""

    ignored_since: float | None = None
    """Monotonic time the current non-compliance streak started (watchdog)."""

    ignoring: bool = False
    """Whether the watchdog currently flags this device (edge for the event)."""

    override_until: float | None = None
    """Monotonic deadline of a manual-override takeover (None = not active)."""

    poor_fit_since: float | None = None
    """Monotonic time the MPC model's fit went (and stayed) poor; debounce."""


@dataclass(frozen=True, slots=True)
class CycleContext:
    """Everything one control cycle resolves once and shares across devices.

    Passed as one bundle so the per-device helpers don't take long runs of
    positional same-typed floats — exactly the argument-swap bug class that
    neither mypy nor tests reliably catch.
    """

    settings: RuntimeSettings
    band: Band
    outdoor: float | None
    dt_min: float
    data: SmartClimateData


def _build_global_input(
    settings: RuntimeSettings,
    band: Band,
    data: SmartClimateData,
    outdoor: float | None,
    *,
    master_off: bool,
) -> GlobalInput:
    """Map the cycle's resolved settings/band/snapshot onto the engine input.

    Pure field mapping — the only logic is the two derived flags (dew-point
    threshold gated by its switch, outdoor gating requiring a reading).
    """
    return GlobalInput(
        band=band,
        release_offset=settings.release_offset,
        tolerance=settings.tolerance,
        home_temp=data.home_avg_temperature,
        home_humidity=data.home_avg_humidity,
        home_trigger=settings.home_average_trigger,
        outdoor_temp=outdoor,
        master_off=master_off,
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
        # Post-restart warm-up bookkeeping: when we started, whether we've yet
        # seen a usable home temperature, and which devices have reported in.
        # Drives the tri-state status so transient startup gaps don't raise
        # repairs or notifications (docs/internals/device-control.md).
        self._started = time.monotonic()
        self._ever_ready = False
        self._seen_available: set[str] = set()
        # Consecutive control-cycle failures (drives the repair issue).
        self._control_failures = 0
        # The last control cycle's resolved settings (see current_settings).
        self._cycle_settings: RuntimeSettings | None = None
        # Flash-wear rate limiting for the learned-state stores: when a save
        # was last scheduled, and the payloads it was scheduled with.

        # All mutable per-device state, one DeviceRuntime per managed entity.
        self._devices: dict[str, DeviceRuntime] = {}
        # The last cycle's decisions, replaced wholesale every control run (so
        # a removed device's decision doesn't linger in reasons/diagnostics).
        self.last_decisions: dict[str, DeviceDecision] = {}
        self._last_cycle: float | None = None
        # Per-area monotonic timestamp of when its window most recently opened,
        # plus a one-shot timer to re-run control when the grace delay expires.
        self._windows = WindowMonitor(hass, self._request_window_recheck)
        # Trailing (time, home-avg-temp) samples and the latest slope (K/min).
        self._temp_samples: deque[tuple[float, float]] = deque(
            maxlen=_SLOPE_MAX_SAMPLES
        )
        self._temp_slope: float | None = None
        # Valve-maintenance bookkeeping (wall-clock epoch of the last run).
        self._maintenance_running = False
        self._last_maintenance: float | None = None
        # Adaptive comfort: running-mean outdoor temp and the shifted band.
        self._adaptation = WeatherAdaptation(hass)
        # Cached hourly outdoor forecast (°C, from the weather entity) for
        # forecast-based preconditioning, plus when it was last fetched.
        # Collaborators: bus events/notifications, and the per-device
        # watchdog + manual-override supervision.
        self._events = EventBridge(hass, entry.entry_id)
        self._supervisor = DeviceSupervisor(hass, entry.entry_id, self._events)
        self._stores = LearnedStateStores(
            hass,
            entry.entry_id,
            mpc_payload=self._mpc_persist_data,
            state_payload=self._state_persist_data,
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
        """Return the device's mutable runtime state, created on first touch.

        Once created, a device's runtime lives until the coordinator unloads
        (or the device is evicted on reconfiguration) — it carries learned
        MPC state, override deadlines, and command history.
        """
        if (runtime := self._devices.get(entity_id)) is None:
            runtime = self._devices[entity_id] = DeviceRuntime()
        return runtime

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

    async def async_load_mpc(self) -> None:
        """Restore persisted MPC + maintenance state (call before first refresh).

        Only currently-managed entities are restored: the persist methods dump
        ``self._devices`` wholesale, so without this filter a device removed
        from the config would cycle store -> runtime -> store forever.
        """
        managed = set(self.device_ids)
        data = await self._stores.load_mpc()
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
        maint = await self._stores.load_state()
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
                self._adaptation.rmot = float(maint["rmot"])
            if isinstance(integral := maint.get("ac_bias_integral"), dict):
                for k, v in integral.items():
                    if k in managed and isinstance(v, int | float) and math.isfinite(v):
                        self._runtime(k).ac_bias_integral = float(v)
            if isinstance(demand := maint.get("last_demand"), dict):
                # StrEnum members compare equal to their string values, so the
                # raw persisted strings can be checked against the enum itself.
                for k, v in demand.items():
                    if k in managed and v in set(Demand):
                        self._runtime(k).demand = Demand(v)

    @callback
    def _state_persist_data(self) -> dict[str, Any]:
        """Slow-state payload; LearnedStateStores calls this and dedupes."""
        return {
            "last": self._last_maintenance,
            "rmot": self._adaptation.rmot,
            "ac_bias_integral": {
                k: rt.ac_bias_integral for k, rt in self._devices.items()
            },
            "last_demand": {k: rt.demand.value for k, rt in self._devices.items()},
        }

    @callback
    def _mpc_persist_data(self) -> dict[str, Any]:
        """Learned-MPC payload; LearnedStateStores calls this and dedupes."""
        return {
            trv_id: controller.to_dict()
            for trv_id, rt in self._devices.items()
            if (controller := rt.mpc) is not None
        }

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
    def last_maintenance(self) -> float | None:
        """Wall-clock epoch of the last valve-maintenance run (diagnostics)."""
        return self._last_maintenance

    @property
    def enabled_presets(self) -> list[str]:
        """Named presets the user chose to expose (default: all)."""
        return enabled_presets(self._options)

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

    def _valve_hints_for(self, entity_id: str) -> tuple[str, ...]:
        """Valve-number hints for a device: its profile's, else the configured."""
        profile = profile_for_entity(self.hass, entity_id)
        return profile.resolve_valve_hints(self.valve_hints)

    def _calibration_hints_for(self, entity_id: str) -> tuple[str, ...]:
        """Calibration-number hints for a device: its profile's, else configured."""
        profile = profile_for_entity(self.hass, entity_id)
        return profile.resolve_calibration_hints(self.calibration_hints)

    async def _async_update_data(self) -> SmartClimateData:
        """Resolve sensors and aggregates, keep listeners in sync, and actuate."""
        max_age_min = clamped_number_value(
            self.hass, self.entry.entry_id, "sensor_max_age"
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
        self._windows.prune(
            r.area_id for r in data.readings.values() if r.area_id is not None
        )
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
        toggle_issue(
            self.hass,
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
            # Missing *or* garbage attributes (restored state is arbitrary
            # JSON) fall back to the active preset's default band.
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
    def _request_window_recheck(self) -> None:
        """Refresh control when a window's grace delay elapses (WindowMonitor)."""
        self._background(self.async_request_refresh(), "window recheck refresh")

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
        number = find_related_number(
            self.hass, entity_id, self._valve_hints_for(entity_id)
        )
        if number is None:
            return []
        self._runtime(entity_id).valve = 0.0
        return [self._write_number_if_changed(number, 0.0)]

    def _mpc_valve_writes(
        self, entity_id: str, area_temp: float | None, ctx: CycleContext
    ) -> list[Coroutine[Any, Any, None]]:
        """Observe the room, optimise the valve opening, and write it."""
        number = find_related_number(
            self.hass, entity_id, self._valve_hints_for(entity_id)
        )
        calibration_issue(self.hass, entity_id, "mpc", missing=number is None)
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
        series = self._adaptation.precondition_series(ctx.dt_min, ctx.settings)

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
        self._evaluate_mpc_fit(entity_id, controller)
        await self._write_number_if_changed(number, pct)

    @callback
    def _evaluate_mpc_fit(self, entity_id: str, controller: MpcController) -> None:
        """Raise/clear the poor-fit repair, debounced over ``MPC_POOR_FIT_SECONDS``.

        A model that can't represent the room — a weather-compensated radiator
        being the usual culprit — fits poorly *persistently*; a cold snap or a
        one-off disturbance recovers. Only a sustained high relative error
        raises the notice.
        """
        runtime = self._runtime(entity_id)
        error = controller.relative_fit_error()
        if error is None or error < MPC_POOR_FIT_RATIO:
            self._clear_poor_fit(entity_id)
            return
        if runtime.poor_fit_since is None:
            runtime.poor_fit_since = time.monotonic()
        sustained = time.monotonic() - runtime.poor_fit_since >= MPC_POOR_FIT_SECONDS
        mpc_poor_fit_issue(self.hass, entity_id, active=sustained)

    @callback
    def _clear_poor_fit(self, entity_id: str) -> None:
        """Reset the MPC poor-fit streak and clear its repair for a device.

        Called both when the fit recovers and when a TRV leaves MPC mode — the
        model assessment no longer applies, so the streak must not linger (a
        stale ``poor_fit_since`` would otherwise re-fire instantly on a later
        switch back to MPC), and any raised repair must clear.
        """
        self._runtime(entity_id).poor_fit_since = None
        mpc_poor_fit_issue(self.hass, entity_id, active=False)

    def _offset_writes(
        self, entity_id: str, area_temp: float | None, adapter: ClimateAdapter
    ) -> list[Coroutine[Any, Any, None]]:
        """Write the local-calibration offset so the TRV sees the area temp."""
        number = find_related_number(
            self.hass, entity_id, self._calibration_hints_for(entity_id)
        )
        calibration_issue(self.hass, entity_id, "offset", missing=number is None)
        offset = local_offset(area_temp, adapter.read().current_temp)
        if number is None or offset is None:
            return []
        return [self._write_number_if_changed(number, offset)]

    @callback
    def _compute_status(self, data: SmartClimateData) -> Status:
        """Classify the orchestrator as initializing / ok / degraded.

        With nothing managed there's nothing to warm up (``OK``). The warm-up
        has two independent legs: a usable home temperature, and every managed
        device having reported in at least once. Area sensors usually beat the
        devices by tens of seconds after a restart, so a still-joining device
        keeps us ``INITIALIZING`` for the rest of the grace window rather than
        flashing ``DEGRADED``. A device that *was* seen and then went away is
        genuine degradation, grace window or not — and once the window elapses,
        whatever is still missing is a real fault (``DEGRADED``).
        """
        if not self.device_ids:
            return Status.OK
        if data.home_avg_temperature is not None:
            self._ever_ready = True
        unavailable = set(data.unavailable_devices)
        self._seen_available |= set(self.device_ids) - unavailable
        in_grace = time.monotonic() - self._started < STARTUP_GRACE_SECONDS
        if unavailable & self._seen_available or not in_grace:
            ok = self._ever_ready and not unavailable
            return Status.OK if ok else Status.DEGRADED
        if self._ever_ready and not unavailable:
            return Status.OK
        return Status.INITIALIZING

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

    @property
    def comfort_influence(self) -> float:
        """The comfort-index humidity influence factor (live)."""
        return clamped_number_value(
            self.hass, self.entry.entry_id, "comfort_humidity_influence"
        )

    @property
    def running_mean_outdoor(self) -> float | None:
        """Running-mean outdoor temperature driving adaptive comfort (°C)."""
        return self._adaptation.rmot

    @property
    def adaptive_band_high(self) -> float | None:
        """Would-be cool edge after the adaptive-comfort shift (preview).

        Only the cool edge is ever relaxed; the heat edge is never touched, so
        there is no matching "low" accessor.
        """
        return self._adaptation.adaptive_band_high

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
        for reason in (
            "window_open",
            "outdoor_gating",
            "manual_override",
            "unavailable",
            "no_data",
        ):
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
    def device_command_attrs(
        self, entity_id: str
    ) -> dict[str, str | float | bool | None]:
        """Return the last command sent to a device (mode + setpoint)."""
        runtime = self._devices.get(entity_id)
        command = runtime.command if runtime else None
        if command is None or runtime is None:
            return {}
        attrs: dict[str, str | float | bool | None] = {
            "commanded_mode": command.hvac_mode.value,
            "commanded_setpoint": command.target_temp,
        }
        if (until := runtime.override_until) is not None:
            attrs["manual_override"] = True
            attrs["manual_override_remaining_min"] = round(
                max(until - time.monotonic(), 0.0) / 60.0, 1
            )
        return attrs

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
            # Excluded this cycle, but its latch is preserved.
            self._supervisor.handle_unavailable(entity_id, runtime)
            return decision, []
        if self._supervisor.override_active(entity_id, runtime, decision):
            # A human adjusted this device: keep deciding (the hysteresis
            # latch stays current for the handback) but write nothing — no
            # command, no MPC observe/valve, no bias update, no watchdog.
            return (
                replace(
                    decision,
                    demand=Demand.IDLE,
                    dry_mode=False,
                    reason="manual_override",
                ),
                [],
            )
        adapter = ClimateAdapter(self.hass, entity_id)
        device_state = adapter.read()
        command = build_command(
            decision,
            kind,
            band=ctx.band,
            ac_setpoint_bias=self._ac_bias(entity_id, kind, decision, reading, ctx),
            caps=adapter.capabilities(),
            tolerance=ctx.settings.tolerance,
            device_current_temp=device_state.current_temp,
            room_temp=self._room_effective(reading, ctx),
        )
        command = self._throttle_ac_setpoint(entity_id, command)
        runtime.command = command
        self._supervisor.watch_compliance(
            entity_id, runtime, device_state.hvac_mode, command.hvac_mode.value
        )
        writes: list[tuple[str, Coroutine[Any, Any, None]]] = [
            (entity_id, adapter.apply(command))
        ]
        if kind is DeviceKind.HEATER:
            if ctx.settings.calibration_mode != CALIBRATION_TARGET:
                writes += [
                    (entity_id, coro)
                    for coro in self._calibration_writes(
                        entity_id, decision, reading, ctx, adapter
                    )
                ]
            if ctx.settings.calibration_mode != CALIBRATION_MPC:
                # Not driving the model this cycle — its poor-fit assessment no
                # longer applies, so drop any streak/repair (it's re-evaluated
                # afresh whenever MPC mode resumes).
                self._clear_poor_fit(entity_id)
        return decision, writes

    @callback
    def _raise_capability_issues(
        self, settings: RuntimeSettings, data: SmartClimateData
    ) -> None:
        """Flag AC-dependent settings that can't act on the configured hardware.

        Capabilities come from each AC's reported ``hvac_modes``, so only
        *available* ACs are inspected (an offline one's modes are unknown).
        """
        ac_ids = self.ac_ids
        available = [
            eid
            for eid in ac_ids
            if (reading := data.readings.get(eid)) is not None and reading.available
        ]
        caps = [ClimateAdapter(self.hass, eid).capabilities() for eid in available]
        capability_issues(
            self.hass,
            settings,
            acs_configured=bool(ac_ids),
            any_available_ac=bool(available),
            any_ac_can_heat=any(c.can_heat for c in caps),
            any_ac_can_dry=any(c.can_dry for c in caps),
            settled=not data.initializing,
        )

    async def _async_control(self, data: SmartClimateData) -> None:
        """Decide per device, apply commands, and run TRV calibration."""
        settings = self._cycle_settings = resolve_settings(
            self.hass, self.entry.entry_id
        )
        await self._adaptation.refresh_forecast(settings, self.weather_entity)
        dt_min = self._cycle_minutes()
        hvac_mode, base_band = self._desired()
        outdoor = self._outdoor_temp()
        band = self._adaptation.apply(base_band, outdoor, settings, dt_min)
        environment_issues(
            self.hass,
            settings,
            data,
            base_band,
            outdoor_sensor=self.outdoor_sensor,
            weather_entity=self.weather_entity,
            has_devices=bool(self.device_ids),
        )
        self._raise_capability_issues(settings, data)
        global_input = _build_global_input(
            settings, band, data, outdoor, master_off=hvac_mode == HVACMode.OFF
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
            eid: self._windows.suppresses(reading, delay_s)
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
        await self._apply_writes(writes)
        self._events.dispatch_cycle(data, window_state, settings, decisions)
        self._stores.maybe_persist()
        self._maybe_auto_maintenance(settings, decisions)

    async def _apply_writes(
        self, writes: list[tuple[str, Coroutine[Any, Any, None]]]
    ) -> None:
        """Run the cycle's writes in parallel, latching per-device failures.

        Every write is isolated (``return_exceptions=True``), so one device
        erroring can never abort the others. Failures log once per outage,
        not once per cycle — a device that stays down would otherwise emit a
        warning every ``UPDATE_INTERVAL``.
        """
        if not writes:
            return
        results = await asyncio.gather(
            *(coro for _, coro in writes), return_exceptions=True
        )
        failures: dict[str, Exception] = {}
        for (entity_id, _), result in zip(writes, results, strict=True):
            if isinstance(result, Exception):
                failures.setdefault(entity_id, result)
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
        self._supervisor.detect_override(event, self._devices, self.device_ids)
        self._background(self.async_request_refresh(), "state-change refresh")

    @callback
    def clear_manual_overrides(self, reason: str) -> None:
        """End every active override (the user reasserted whole-home intent)."""
        self._supervisor.clear_overrides(self._devices, reason)

    # --- Services / maintenance ---------------------------------------------

    async def async_reset_mpc(self, trv_ids: list[str] | None = None) -> None:
        """Forget learned MPC state for some/all TRVs and re-run control."""
        targets = trv_ids or self.trv_ids
        for trv_id in targets:
            if (runtime := self._devices.get(trv_id)) is not None:
                runtime.mpc = None
                runtime.valve = None
        await self._stores.save_mpc_now()
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
            if (
                number := find_related_number(
                    self.hass, trv_id, self._valve_hints_for(trv_id)
                )
            )
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
            await self._stores.save_state_now()
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
        if self._last_maintenance is not None and self._last_maintenance > now:
            # Wall-clock skew (NTP correction, restored backup from another
            # box): a future timestamp would silently defer maintenance for
            # up to a full interval past the lie — restart the clock instead.
            self._last_maintenance = now
        if self._last_maintenance is None:
            # First run after install: start the clock rather than acting now.
            self._last_maintenance = now
            self._background(self._stores.save_state_now(), "maintenance clock save")
            return
        if now - self._last_maintenance < settings.valve_maintenance_interval * 86400:
            return
        trvs = set(self.trv_ids)
        if any(d.demand is Demand.HEAT for key, d in decisions.items() if key in trvs):
            return  # don't interrupt active heating
        self._background(self._auto_maintenance(), "auto valve maintenance")

    async def _auto_maintenance(self) -> None:
        """Run due auto maintenance, surfacing the found-no-valves case.

        ``async_run_valve_maintenance`` returning False means no valve
        opening numbers were found (hint mismatch, devices renamed). Left
        alone, the run would stay "due" and respawn a silent no-op every
        cycle — restart the clock instead and say why, once per interval.
        """
        if await self.async_run_valve_maintenance():
            return
        self._last_maintenance = time.time()
        await self._stores.save_state_now()
        _LOGGER.warning(
            "climate_orchestrator: auto valve maintenance found no valve"
            " opening numbers on the configured TRVs; retrying next interval"
            " (check the valve discovery hints)"
        )

    async def async_shutdown(self) -> None:
        """Cancel listeners, flush MPC state, and shut the coordinator down."""
        if self._unsub_state is not None:
            self._unsub_state()
            self._unsub_state = None
        self._windows.shutdown()
        # Per-device repairs are keyed by entity id; without this they outlive
        # an entry unload/removal as orphaned notices for devices that are gone.
        for entity_id in self.device_ids:
            mpc_poor_fit_issue(self.hass, entity_id, active=False)
            calibration_issue(self.hass, entity_id, "mpc", missing=False)
            command_ignored_issue(self.hass, entity_id, active=False)
        if any(rt.mpc is not None for rt in self._devices.values()):
            await self._stores.save_mpc_now()
        # The rate limiter may be holding back slow-moving state — flush it
        # now that we're going away for real.
        await self._stores.save_state_now()
        await super().async_shutdown()
