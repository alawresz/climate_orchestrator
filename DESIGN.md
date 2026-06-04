# Climate Orchestrator — Design Document

**Domain:** `climate_orchestrator`
**Status:** Draft for review (v0.1)
**Target Home Assistant:** 2024.12+ (matching current `pytest-homeassistant-custom-component` support)

A Home Assistant custom integration that exposes a **single, whole-home smart climate entity** which orchestrates every radiator valve (TRV) and air-conditioner in the house. It picks the right device(s) to run based on per-area sensors *and* a home-wide average, coordinates heating against cooling so they never fight, uses humidity for comfort, and drives TRVs with an improved Model Predictive Controller. It is built test-first with modern tooling.

---

## 1. Goals and non-goals

### Goals

- One whole-home `climate` entity as the control surface; areas are handled internally.
- Manage any number of TRVs and AC units, chosen in the UI config flow.
- Match each managed device to the temp/humidity sensors of its **HA area**, plus maintain a **home-wide average** across all in-use sensors.
- Asymmetric trigger logic: engage on *local OR home-average* threshold crossing; release only when *both* are satisfied (with a deadband early-out).
- Two setpoints (a heating edge + a cooling edge) defining a neutral band; coordinated heat/cool with anti-fighting.
- Presets carrying heating and cooling thresholds with adjustable min/max bounds.
- Humidity-aware control via a "feels-like" comfort index, plus a dew-point safety guard.
- MPC calibration for TRVs (with the scipy-based improvements below) and an offset/bias path for both TRVs and ACs.
- Expose behavioural settings as **toggle/number/select entities on the device**, not buried in config.
- **Resilient to individual device/sensor dropouts** — one TRV or AC (or sensor) going offline never takes down the whole-home entity (§6.4).
- Excellent automated test coverage.

### Non-goals (v1)

- No per-room separate climate entities (explicitly chosen: single whole-home entity).
- No valve summer-maintenance feature (de-scoped by request).
- No cloud dependencies; everything runs locally against existing HA entities.
- Radiators own heating by default; AC heating is opt-in via the `ac_heating_assist` toggle (only when the unit supports `heat`).

---

## 2. Target hardware

The integration is built around two classes of `climate` device, distinguished by *how* each can be steered:

| Class | Representative devices | Control levers |
|-------|------------------------|----------------|
| **Radiator valve (TRV)** | Zigbee thermostatic valves such as the SONOFF TRVZB (via Zigbee2MQTT) | valve opening % (0–100), `local_temperature_calibration`, and a normal setpoint |
| **Air conditioner** | mini-split / window / portable units (e.g. Midea-class) | setpoint, mode, fan, swing — **setpoint-only**, no sensor-offset lever |

Design implication: TRVs support *both* valve control and sensor-offset calibration; an AC supports *neither* — only setpoint, mode, fan, swing. The device abstraction must accommodate both control philosophies (see §6). Any HA `climate` entity in these classes works: the adapter reads each device's reported capabilities (heat/cool/dry, setpoint range and step) at runtime and drives only what it actually supports.

---

## 3. High-level architecture

```
                         ┌──────────────────────────────┐
                         │  climate.climate_orchestrator │  (single whole-home entity)
                         └───────────────┬───────────────┘
                                         │ target, mode, preset
                         ┌───────────────▼───────────────┐
                         │     SmartClimateCoordinator     │  (DataUpdateCoordinator)
                         │  - holds shared runtime state   │
                         │  - runs the control loop        │
                         └───┬───────────┬──────────────┬──┘
                  sensor data │           │ control law  │ device commands
        ┌────────────────────▼──┐   ┌─────▼──────────┐  ┌▼─────────────────────┐
        │  sensing.build_snapshot│   │  control.engine│  │  ClimateAdapter / dev │
        │  - area→sensor map     │   │   .decide      │  │  - TRV: MPC valve /   │
        │  - staleness guard     │   │  - comfort idx │  │    local offset       │
        │  - home-wide average   │   │  - hysteresis  │  │  - AC: setpoint bias  │
        └────────────────────────┘   └────────────────┘  └──────────────────────┘
                                         │
                         ┌───────────────▼───────────────┐
                         │  Companion entities (per device entry):              │
                         │  switch/number/select/sensor exposing feature flags  │
                         │  and tunables (see §8)                               │
                         └──────────────────────────────────────────────────────┘
```

**Why a coordinator.** A single `DataUpdateCoordinator` (`SmartClimateCoordinator`) owns the shared runtime state (current sensor readings, aggregates, learned MPC state, feature-flag values) and runs one control cycle per trigger. All entities (the climate entity, switches, numbers, sensors) read from the coordinator. This avoids the a prior-art integration "god-object" by keeping the `ClimateEntity` thin and pushing logic into testable, dependency-light modules (the pure `control/` package, the `sensing/` snapshot builder, and per-TRV `MpcController`s), with all device I/O behind a `ClimateAdapter`.

**Control cycle triggers.** A control cycle runs on: any subscribed sensor change, any managed-device state change, target/preset/mode change, a feature-flag entity change, and a periodic keepalive (`UPDATE_INTERVAL_SECONDS`, default 60 s, to re-assert offsets and run MPC).

---

## 4. Sensor matching and aggregation

### 4.1 Area sensor resolution

Home Assistant lets each **area** declare its own temperature and humidity sensor (Settings → Areas → *Related sensors*; stored on the area registry as `temperature_entity_id` / `humidity_entity_id`). We use that as the source of truth rather than scanning entities by `device_class`:

1. For each managed climate device, resolve its **area** (device area, else entity area).
2. Read the area's **configured** temperature/humidity sensor from the area registry. That single entity *is* the area's local temperature/humidity — no guessing or averaging of arbitrary `sensor` entities.
3. If an area has **no configured sensor**, the device's local value **falls back to the home-wide average** (§4.2) — not to the device's own internal reading.
4. Re-resolved on area-registry updates, so changing an area's sensor in the UI takes effect without reconfiguring the integration.

### 4.2 Home-wide average

The **home average** = mean across all temperature (and, separately, humidity) sensors actually in use by the integration (i.e. the union of all matched area sensors), recomputed each cycle. Exposed as read-only `sensor` entities (`sensor.climate_orchestrator_home_avg_temperature`, `..._home_avg_humidity`) for visibility and automations.

**User override.** The config/options flow accepts optional whole-home average temperature/humidity sensors (`home_temperature_sensor` / `home_humidity_sensor`, e.g. covering rooms without managed devices). When set, the override replaces the computed mean everywhere downstream — engine home-side trigger, no-area-sensor fallback, AC bias room fallback, slope, feels-like display. The override is read through the same resolve path as every other sensor, so the staleness guard applies; if it's unavailable, non-numeric, non-finite (`nan`/`inf` parse as floats without raising — every numeric read funnels through `util.as_float`, which rejects them), or stale, the *computed* mean stands in (keeping status/repairs truthful and control alive). Each reading's provenance is carried on the snapshot (`SmartClimateData.home_temp_source`/`home_humidity_source`: `computed`/`external`/`fallback`) and surfaced by the `home_avg_source` ENUM diagnostic (`mixed` headline when the two differ, per-reading detail in attributes).

Optionally area-weighted in a later phase; v1 uses a simple mean.

---

## 5. Control model

### 5.1 Setpoint: two setpoints (a heating/cooling band)

The whole-home entity is a `heat_cool` climate that exposes **two setpoints** via `TARGET_TEMPERATURE_RANGE`: a low handle = **heating edge** `T_heat` and a high handle = **cooling edge** `T_cool`. Together they define the band:

- **Heat** when measured `< T_heat`; **cool** when measured `> T_cool`.
- **Neutral zone:** `T_heat ≤ measured ≤ T_cool` → no actuation. The gap between the edges structurally prevents simultaneous heat+cool demand.
- The hysteresis "target" `T` (§5.2 release threshold) is the band midpoint `(T_heat + T_cool) / 2`.

Presets set both edges (see §7); a manual `set_temperature` sets the two handles directly. (Earlier drafts used a single target + a `deadband` number to derive the edges; the two-setpoint model supersedes it and the `deadband` entity was removed.)

### 5.2 Asymmetric hysteresis (the core trigger law)

For each managed device, let `x_local` be its area value and `x_home` the home average. Using the **comfort-adjusted** temperature (§5.3) as `x`:

**Cooling demand for a device:**

Let `T_cool_target = max(T_cool − tolerance, T)` and `T_heat_target = min(T_heat + tolerance, T)` (each capped at the midpoint `T` so they can't cross).

```
ENGAGE  when  x_local > T_cool  OR  x_home > T_cool
STAY ON until (x_local ≤ T_cool_target  AND  x_home ≤ T_cool_target)
        OR    x_local ≤ T_heat + release_offset         # opposite-edge early-out
```

**Heating demand (mirror):**

```
ENGAGE  when  x_local < T_heat  OR  x_home < T_heat
STAY ON until (x_local ≥ T_heat_target  AND  x_home ≥ T_heat_target)
        OR    x_local ≥ T_cool − release_offset
```

- A device **engages at the trigger edge** and drives to `edge ± tolerance` (the control target), so rooms settle just inside the comfort edge (efficient end of the band) rather than at the midpoint. The same setpoint is what's commanded to the device (§6.1/§6.2).
- `tolerance` is a configurable `number` entity (default 0.3 K). The engage-at-edge / release-past-edge gap *is* the anti-short-cycle hysteresis, so jitter at an edge can't toggle a device and a minimum on/off gap holds even for a narrow band. Capping the targets at the midpoint keeps heat/cool from fighting.
- `release_offset` is a configurable `number` entity (default 0.5 K): a secondary early-out that stops cooling once a room has dropped near the heating regime (and vice-versa), preventing a device from dragging its room across the neutral zone.
- The OR-to-engage / AND-to-release asymmetry makes the system eager to respond to a hot/cold room or a hot/cold house, but conservative to disengage — which suppresses short-cycling.
- Per-device demand state is latched in coordinator state so hysteresis survives cycles. All of a device's mutable bookkeeping — the demand latch, last command, AC-setpoint throttle state, MPC controller, last valve fraction, bias integral, and runtime samples — lives on a single per-device `DeviceRuntime` object (`coordinator.py`), so init and cleanup are atomic.

### 5.3 Comfort index (humidity use)

Control runs off a **feels-like** temperature rather than raw dry-bulb, when humidity is available:

- **Formula — Apparent Temperature (AT).** The Australian Bureau of Meteorology AT: `AT = T + 0.33·e − 0.70·ws − 4.00`, where `e` is water-vapour pressure from `T` and RH and `ws` is wind speed (0 indoors → `AT = T + 0.33·e − 4.00`). Unlike the US Heat Index it's a single continuous function across the whole indoor range, covering both heating and cooling with no branching. Higher humidity pushes AT up (cool earlier / longer); the humidity contribution is small at low temperatures, so heating stays near dry-bulb. Used on the *actual* RH (no rebaselining) — that matches how a person experiences the room.
- Because AT can differ noticeably from the dry-bulb number a user sets, the whole-home AT is **surfaced as its own `sensor` (`home_feels_like_temperature`)** next to the plain average, so it's visible *why* the thermostat is running when the dry-bulb reading looks fine.
- Implementation: pure `vapour_pressure`, `apparent_temperature`, `dew_point`, and `effective_temperature`. `effective_temperature` **blends dry-bulb toward AT by a configurable influence**: `effective = T + k·(AT − T)`, where `k` is the `comfort_humidity_influence` number (default 1.0 → full AT; `0` → dry-bulb, i.e. humidity ignored; `>1` amplifies). It returns dry-bulb when comfort is off or humidity is missing. `effective_temperature` feeds `x_local`/`x_home` in §5.2 (engine threads `k` via `GlobalInput.comfort_influence`); the `home_feels_like_temperature` sensor and the climate entity's `current_temperature` use the same blended value, so the displayed feels-like always matches what control judges against. A `switch` disables comfort targeting and falls back to dry-bulb.

**Adaptive cooling comfort (§5.6, opt-in):** an optional, *cooling-only* relaxation of the cool edge driven by the outdoor temperature. A running-mean outdoor temperature (exponential smoother, ~1-day time constant, persisted) is compared against an **onset** = `cool_edge + bias` (`adaptive_cooling_comfort_onset_bias`, default +1 K). The cool edge then rises by a smooth **saturating** amount of the outdoor *excess* over that onset, capped at `adaptive_cooling_comfort_max_shift` (default 2 K):

```
excess     = max(0, RMOT − (cool_edge + bias))
cool_shift = max_shift · (1 − exp(−excess / response))
adaptive_cool = cool_edge + cool_shift
```

`adaptive_cooling_comfort_response` (default 5 K) is the characteristic degrees of excess for ~63% of the cap, so a larger value gives a gentler ramp; the curve starts at zero at the onset, rises with an ever-decreasing slope, and asymptotically approaches (never reaches) the cap — no jump, no hard plateau. The **heat edge is never touched**, so a device is never driven harder than the preset, and nothing shifts when it's milder outside than the onset. This replaced an earlier EN 16798 neutral-referenced model whose warm-leaning neutral (≈24.4 °C at `T_rm`=17) raised the cool edge even at mild outdoor temperatures — exactly the behaviour we wanted gone (relaxing cooling only when it's genuinely hot out). Pure functions in `control/adaptive_comfort.py`. The shifted band is *always computed* (surfaced via the `adaptive_cool_setpoint` sensor for preview — there's no heat-setpoint sensor since the heat edge never moves) but only *applied* to control when the `adaptive_cooling_comfort` switch is on. `running_mean_outdoor_temperature` is exposed as a diagnostic sensor.

**Dew-point guard (safety trigger):** independently of the temperature band, if the area dew point exceeds a configurable threshold (`number`, default e.g. 16 °C), the guard can (a) request the AC `dry` mode and/or (b) flag a binary sensor for automations. Pure function `dew_point(temp_c, rh_pct)`. Toggle entity to enable/disable.

### 5.4 Heat/cool coordination

A single arbiter decides the whole-home `hvac_action` each cycle:

1. Compute per-device heating and cooling demand (§5.2).
2. Global guards in priority order: **window-open** (suppress the affected area — detected automatically from `window`/`door`/`opening`/`garage_door` `binary_sensor`s in the device's area, after an optional grace delay; see §6.5; **coolers can be exempted** via `ac_ignore_window` for a portable/exhaust-hose split that needs its window open to vent — heaters are never exempted), **frost protection** (force heating if any area below frost temp, overrides everything), **outdoor-temp gating** (see §5.5).
3. Mutual exclusion: a device cannot heat and cool simultaneously; the neutral deadband normally guarantees this, and the arbiter asserts it as an invariant (unit-tested).
4. Build each device's command (`devices/command.py`) and dispatch it through that device's `ClimateAdapter`.

**AC heating assist.** Radiators own heating by default. If the `ac_heating_assist` toggle is on and an AC supports `heat`, the arbiter may also command that AC to heat — configurable as *supplement* (engage when an area's heating demand persists and its radiators are saturated) or *substitute* (areas with an AC but weak/no TRV coverage). Still bound by the single-target band and the heat/cool mutual-exclusion invariant.

### 5.5 Outdoor-temp gating

Outdoor temperature comes from a **user-selected outdoor sensor** (e.g. simply point this at the AC's outdoor-temperature sensor), with an optional **weather-entity forecast** as the only fallback. Behaviour (toggle entity):

- Suppress **heating** when outdoor ≥ `heat_off_outdoor` threshold.
- Suppress **cooling** when outdoor ≤ `cool_off_outdoor` threshold.

This is the one cross-cutting coordination a prior-art integration lacked on the cooling side; here both paths are outdoor-aware.

---

## 6. Device control strategies

A common `DeviceAdapter` interface decouples control from integration specifics:

```python
class DeviceAdapter(Protocol):
    capabilities: AdapterCapabilities      # supports_valve, supports_local_offset, setpoint_only, hvac_modes...
    async def read(self) -> DeviceState: ...
    async def apply(self, command: DeviceCommand) -> None: ...
```

Concrete adapters: `Z2MTrvAdapter` (SONOFF TRVZB) and `MideaAcAdapter`, plus a `GenericClimateAdapter` fallback (any HA `climate` entity). Adapter selection is capability-based, not vendor-locked.

**Hardware portability.** In the implementation, a single `ClimateAdapter` drives *any* HA `climate` entity (TRV or AC): `can_heat/can_cool/can_dry`, `min_temp`/`max_temp`/`target_step` are all read from the device's own reported attributes, so adding a different AC or a standard TRV needs no code change. The only hardware-coupled assumption is *discovering a TRV's `valve_opening_degree` / `local_temperature_calibration` `number` entities* for `mpc`/`offset` modes, which is done by name-matching (`find_related_number`). Those name hints default to Zigbee2MQTT/SONOFF naming but are **user-configurable** in the options flow (`valve_opening_hints` / `calibration_hints`, comma-separated; parsed to a lower-cased tuple by the coordinator), so another brand's naming can be supported without code changes. `target` mode (the default) needs none of this.

### 6.1 TRV controller — MPC + offset

- **Primary:** Model Predictive Control computing a **valve opening %** (the TRVZB accepts it directly). When the device is not heating (idle/off/window/gated), the valve is explicitly driven to **0%** rather than left at its last commanded opening — otherwise a TRV can linger open and keep heating (a recurring failure mode in comparable integrations). NB: `valve_opening_degree` semantics are firmware-dependent on the TRVZB, so MPC remains hardware-unvalidated; `target` is the safe default.
- **Secondary/fallback:** `local_temperature_calibration` offset — feed the TRV a biased local temperature (true measured − external truth) so its internal loop keeps the valve open until the *room* reaches target. Used when valve control is unavailable or as a complement.
- **Forecast preconditioning (opt-in, `forecast_preconditioning`, MPC mode only).** Normally the optimiser plans against the current outdoor temperature held flat. With this on, the coordinator fetches the configured weather entity's **hourly** forecast (via `weather.get_forecasts`, cached and refreshed at most every `PRECONDITION_FORECAST_REFRESH_SECONDS`), interpolates it onto the control step over `preconditioning_horizon` hours (`control/forecast.py: expand_forecast`, capped at `PRECONDITION_MAX_STEPS`), and feeds that **per-step outdoor series** into `optimize_valve` over the extended horizon — so a radiator pre-heats ahead of a forecast cold spell. To stay comfort-safe it can only *raise* the valve: the commanded opening is `max(react-to-now valve, forecast valve)`, never less (the pure `preconditioned_valve_pct` in `control/mpc/controller.py`). `optimize_valve`/`compute_valve_pct` accept `outdoor` as either a scalar or a sequence (a shorter series holds its last value). The fetch is best-effort (failures no-op); a missing weather entity raises a repair.
- See §9 for the MPC spec.

### 6.2 AC controller — setpoint bias + offset

The Midea AC has no sensor-offset lever, so the equivalent trick is **setpoint biasing**:

- To keep cooling until the *room* (external sensor) hits target, command the AC a setpoint **below** the cool target by a bias, so the AC's own indoor sensor doesn't prematurely satisfy.
- **Self-tuning AC bias (default on, `self_tuning_ac_bias`):** integral feedback (`control/adaptive_bias.py`). While the AC is actively cooling and the room is above target, an accumulator integrates `Ki · error · dt` and adds to the manual base bias; when not cooling it decays. Anti-windup clamps the add-on to `[0, max − base]`. The manual `ac_setpoint_bias` is the floor; `ac_setpoint_bias_max` is the ceiling. This auto-tunes the steady-state offset a fixed bias only approximates and removes manual tuning. Per-AC accumulator lives in coordinator state (in-memory; re-learns in minutes after a restart).
- **Compressor anchoring (proportional):** an AC only runs its compressor when the commanded setpoint is below what *its own* internal sensor reads — otherwise it idles/fans. Whenever cooling is wanted, `build_command` anchors the setpoint to the AC's reported temperature, pushed down by `max(room_above_target, AC_COOL_KICK)` where `room_above_target = room_eff − cool_target`. So the depth scales with how far the room is above target: a room 3 °C over target drives the AC ~3 °C below its own reading (cool hard), while a room just over target gets the `AC_COOL_KICK` (1 °C) floor (enough to keep the compressor on). The final setpoint is `min(cool_target − bias, internal − drive)` — the room-sensor calc still caps it. The room sensor (via the engine releasing the demand) ends the call. This is the AC equivalent of the TRV offset/MPC trick, and is why the fixed bias alone wasn't enough when the AC's own sensor sat below the room.
- Every commanded setpoint is clamped to the device's reported `min_temp/max_temp` and snapped to its step in `build_command` (`_clamp`), so even a large bias can't drive an AC below the minimum it accepts.
- **Write throttling (`control/throttle.py`):** the proportional anchor nudges the setpoint most cycles, so re-issuing it each time would flood the AC's radio. `_throttle_ac_setpoint` holds the last written value unless it moved ≥ `AC_SETPOINT_MIN_CHANGE` (0.5 °C) **and** ≥ `AC_SETPOINT_MIN_INTERVAL_SECONDS` (180 s) elapsed, with an `AC_SETPOINT_KEEPALIVE_SECONDS` (900 s) re-assert; held values become reconcile no-ops. The throttle resets on any non-cooling command (so re-engaging cooling writes fresh). It complements the per-step diff in `reconcile` — the step diff drops sub-step jitter, the throttle adds a time floor on ≥-step drift.
- Mode selection: cooling demand → `cool` (or `dry` under the dew-point guard); off when no demand and hysteresis released.
- **Fan & swing passthrough:** if the AC advertises `fan_modes`/`swing_modes`, those are surfaced on the whole-home climate entity and forwarded to the AC(s) that support them.
- **Heating assist (optional):** when `ac_heating_assist` is enabled and the AC supports `heat`, the AC participates in heating per §5.4.

This directly satisfies the requirement to "add similar logic to AC as to TRVs (offset so the internal AC temp matching target doesn't prevent cooling)."

### 6.3 Idempotent commands (update minimization)

Every adapter command passes through a diff against the device's last-known state; a service call is issued **only when something actually changes**:

- Skip setpoint writes when the desired value equals the current value within the device's step (e.g. 0.5 °C, or 1 % valve opening).
- Skip mode/fan/swing writes when the device is already in the requested state.
- Coalesce all triggers within one control cycle into at most one write per device, and debounce rapid sensor chatter.
- Cache last-commanded values in the coordinator and reconcile against reported state, so we neither spam devices nor fight manual/external changes.

This minimises Zigbee/RF and cloud traffic and extends TRV battery life.

### 6.4 Device availability & graceful degradation

The single whole-home entity must never go dark because one device dropped off. Each managed device and sensor is tracked independently:

- A TRV or AC reporting `unavailable`/`unknown` (or missing entirely) is **excluded from the current control cycle**; the remaining devices keep being controlled normally.
- The whole-home `climate` entity stays **available** as long as at least one managed device *or* a usable temperature source remains. It reports `unavailable` only if everything it could act on is gone.
- The **home-wide average** (§4.2) and any area aggregate are computed over *available* sensors only — an offline sensor is dropped from the mean rather than poisoning it (and an area whose configured sensor is offline falls back to the home average per §4.1).
- Every device command is isolated: dispatched per-device and gathered with `return_exceptions=True`, so a timeout or error talking to one device is caught, logged, and contained — it can never abort the cycle for the others.
- Degraded status is surfaced for visibility: the diagnostic `status` sensor reads `degraded` and lists which devices are currently excluded in its `unavailable_devices` attribute. Devices rejoin automatically when they return.
- Learned MPC/observer state for an absent device is **retained, not reset**, so it resumes cleanly on reconnect.
- **Post-restart warm-up.** A tri-state `status` (`initializing` / `ok` / `degraded`) gates startup noise. Right after a restart, devices and their area sensors typically haven't reported in yet, so the coordinator reports `initializing` for a grace window (`STARTUP_GRACE_SECONDS`, 120 s) until a managed device first yields a usable temperature. While `initializing`, the **transient** repairs (`no_temperature_source`, `stale_sensor`) are held back and `status` reads `initializing` rather than `degraded` — they would otherwise flash on every restart. The instant a usable reading arrives the warm-up ends for good (`ok`, or `degraded` if a device is unavailable); if the window elapses with still no reading the gap is real, so `status` becomes `degraded` and the missing-source repair fires. Static misconfigurations (inverted band, adaptive comfort without an outdoor sensor) are *not* startup-transient and fire immediately. `build_snapshot` sets a warm-up-unaware best-effort status; the coordinator refines it. The `degraded` property is now `status is DEGRADED`.

Explicitly covered in the test plan (§12).

### 6.5 Window-open grace delay

The window-open guard (§5.4) is debounced by a configurable **Window open delay** (`number`, minutes; default `0` = stop immediately). When an area's window opens, the coordinator records the open timestamp; the guard only suppresses that area's heating/cooling once the window has stayed open for at least the delay, so a brief airing doesn't interrupt an in-progress heat-up. The rule itself is a pure predicate (`control/window.py`, `window_suppresses(raw_open, opened_at, now, delay)`) over coordinator-owned per-area timing state, which keeps it trivially unit-testable. To avoid waiting for the next keepalive, opening a window schedules a one-shot `async_call_later` refresh that re-runs control right when the delay elapses. Frost protection still overrides an open window regardless of this delay.

---

## 7. Presets

Presets are first-class and persisted. The active comfort **band is defined directly by its two edges** — heat below the lower edge, cool above the upper edge, neutral between:

| Field | Meaning | Exposed as |
|-------|---------|-----------|
| `min` | lower band edge — heat when measured < `min` | `number.climate_orchestrator_preset_<name>_min` |
| `max` | upper band edge — cool when measured > `max` | `number.climate_orchestrator_preset_<name>_max` |

So `min`/`max` *are* the heating and cooling thresholds; the §5.1 single-target+deadband form is just the manual equivalent (`min = T − d`, `max = T + d`).

**Default presets:** `Away`, `Home`, `Sleep` (edge values configurable; e.g. Away 16/26, Home 20/24, Sleep 18/23). Selecting a preset applies its edges; a manual temperature set on the climate entity switches to a "manual" band derived from the single target + deadband and remembers the last preset. All preset edges are `number` entities that persist across restarts (RestoreEntity / coordinator store).

**What the climate entity *displays* vs. *controls*.** To keep the thermostat card consistent with the control loop, the entity shows what control actually uses: `current_temperature` is the feels-like (apparent) temperature whenever `comfort_index_targeting` is on (else dry-bulb), and `target_temperature_high` is the adaptive-comfort-relaxed cool edge whenever `adaptive_cooling_comfort` is on (`target_temperature_low`/heat edge is never shifted). The *underlying* values are always carried as state attributes — `dry_bulb_temperature` (raw home average) and `base_target_temp_low`/`base_target_temp_high` (the user-set band). Crucially, the coordinator's `_desired()` reads the **base** band back from those attributes, not from `target_temp_high`; otherwise the displayed (already-shifted) cool edge would be re-shifted every cycle into a runaway. Setting a temperature stores the *base* band as before, so dragging the cool handle while a shift is active makes it re-snap to `new base + current shift`.

---

## 8. Entities exposed (feature flags as entities)

Per the requirement to keep behaviour as device entities rather than config. The list below reflects what is **implemented**; aspirational extras are noted at the end.

**Climate (1):** `climate.climate_orchestrator` — preset, current temp/humidity (home aggregates), `hvac_action`, plus `fan_mode`/`swing_mode` when any managed AC advertises them (forwarded to those ACs). The **mode and setpoint shape adapt to the configured hardware**: TRVs + an AC → `heat_cool`/`off` with **two setpoints** (`TARGET_TEMPERATURE_RANGE`); TRVs only → `heat`/`off` with one setpoint (`TARGET_TEMPERATURE`); AC only → `cool`/`off` with one setpoint (or `heat_cool` once **AC heating assist** is enabled — the AC is then heat-capable). Heating capability is `has_TRV or (has_AC and ac_heating_assist)`; the reported `hvac_mode` is normalised to a valid on-mode so toggling assist can't leave a stale mode. Internally control always works on a two-edge band: a single-purpose setup pins the unused edge to the device limit (`MIN_TEMP`/`MAX_TEMP`), so the one real setpoint behaves like an ordinary thermostat target and the band can never look inverted.

**Switches (toggles):** `comfort_index_targeting`, `home_average_trigger` (default on; off = each room engages/releases on its own reading only — §5.2), `dew_point_guard`, `window_open_detection`, `ac_ignore_window` (default off — exempt coolers from window suppression for a portable/exhaust-hose split), `outdoor_temp_gating`, `frost_protection`, `ac_heating_assist`, `self_tuning_ac_bias` (default on), `auto_valve_maintenance` (default off), `adaptive_cooling_comfort` (default off), `forecast_preconditioning` (default off; §6.1).

**Services (entity services on the whole-home `climate` entity, registered under the `climate_orchestrator` domain):** `run_valve_maintenance` (drive each TRV valve fully open then closed via its `valve_opening_degree`, dwelling at each extreme, then restore normal control — re-entrancy guarded; optional `trvs:` scope) and `reset_mpc_learning` (drop the persisted `MpcController` state for some/all TRVs). `auto_valve_maintenance` runs the former on a `valve_maintenance_interval`-day cadence, only when no TRV is actively heating; the last-run timestamp is persisted so it survives restarts and doesn't fire on every boot.

**Numbers (tunables):** `release_offset`, `tolerance` (overshoot-past-trigger target; default 0.3 K), `comfort_humidity_influence` (blend factor on the comfort index; default 1.0, unitless), `heat_off_outdoor` (default 20 °C), `cool_off_outdoor` (default 16 °C), `dew_point_threshold`, `frost_protection_temp`, `ac_setpoint_bias` (adaptive floor), `ac_setpoint_bias_max` (adaptive ceiling), `window_open_delay`, `valve_maintenance_interval` (days), `adaptive_cooling_comfort_max_shift`, `adaptive_cooling_comfort_onset_bias` (onset offset; default +1 K), `adaptive_cooling_comfort_response` (ramp gentleness; default 5 K), `sensor_max_age` (staleness timeout, minutes; default 360 = 6 h, 0 disables), `preconditioning_horizon` (forecast look-ahead, hours; default 2, §6.1).

**Select:** `calibration_mode` — `target` (mode + setpoint, default), `mpc` (drive valve via MPC), `offset` (bias local temperature).

**Sensors (home-wide, primary):** `home_avg_temperature`, `home_avg_humidity`, `home_feels_like_temperature` (apparent temperature of the home average — explains comfort-driven runs), `temperature_slope` (K/min, least-squares over a trailing window of the home average; see `control/slope.py`), `adaptive_cool_setpoint` (the cool edge after the adaptive cooling-comfort shift; §5.6 — the heat edge never moves, so there's no matching heat sensor). Diagnostic adaptive-comfort input: `running_mean_outdoor_temperature`. Diagnostic provenance: `home_avg_source` (ENUM `computed`/`external`/`fallback`/`mixed` — §4.2 user override).

**Sensors (per-TRV MPC diagnostics):** `<trv>_mpc_heating_gain` (K/min), `<trv>_mpc_heat_loss` (1/min), `<trv>_mpc_learning_status` (`idle`/`learning`/`ready`), `<trv>_mpc_model_error` (RMS fit residual in K, from `MpcController.fit_rmse()` — a model-confidence figure) — read straight from the learned `MpcController`; only populated in `mpc` mode.

**Sensors (per-device diagnostics, all managed devices):** `<device>_device_action` (ENUM idle/heating/cooling/drying/off/unavailable, with the last commanded mode + setpoint as attributes), `<device>_device_runtime` (% of the trailing hour the device ran), `<device>_device_cycles_per_hour` (off→on starts/hour over that window — surfaces short-cycling), and `<trv>_valve_position` (last commanded valve %, TRV-only). The runtime/cycle counters are computed from a rolling deque of `(monotonic, running?)` samples kept per device in the coordinator and integrated by the pure (mutation-tested) `control/runtime_stats.py` (window `RUNTIME_WINDOW_SECONDS`, transient — not persisted).

**Sensor (diagnostic):** `hvac_action_reason` — an ENUM headline of *why* the home is heating/cooling/idle (`heating`, `cooling`, `dehumidifying`, `frost_protection`, `window_open`, `outdoor_gating`, `unavailable`, `idle`, `off`), with per-device reasons as attributes. The engine's `DeviceDecision.reason` feeds it; the coordinator aggregates a headline.

**Sensor (diagnostic):** `status` — an ENUM (`initializing` / `ok` / `degraded`) of the orchestrator's overall health, driving the post-restart repair suppression in §6.4. Any offline managed devices are listed in its `unavailable_devices` attribute. (This subsumes the former `degraded` binary sensor, which was fully derivable from it.)

**Binary sensors:** operational (non-diagnostic, dashboard-friendly) `window_open` (any managed area reports a window/door open; open areas in attributes), `frost_active` (a device is in forced frost-protection heat), `dew_point_active` (an AC is running dry mode for the dew-point guard).

**Sensor staleness guard (§6.4).** `build_snapshot` takes a `max_age_seconds` (from the `sensor_max_age` number) and an injectable `now`; an area sensor whose `last_reported` (falling back to `last_updated`) is older than the max age is treated as **missing** — its value is dropped (so the home average and the device fall back exactly as for an offline sensor) and its id is collected into `SmartClimateData.stale_sensors`. This stops a frozen-but-"available" sensor (a common Zigbee failure) from silently driving control on a stale value. The set surfaces in diagnostics and raises the `stale_sensor` repair; `0` disables the guard. Measuring from `last_reported` (not `last_changed`) means a legitimately stable temperature isn't mistaken for stale.

**Diagnostics & repairs:** a `diagnostics.py` platform exposes a downloadable dump (merged config, resolved settings, the latest snapshot incl. `stale_sensors`, per-device decisions/reasons, per-device action/runtime/cycles/valve, learned MPC params, adaptive state). Repairs **issues** are raised (and auto-cleared) for silent misconfigurations: a TRV in `mpc`/`offset` mode with no discoverable valve/calibration number (falls back to `target`); adaptive cooling comfort enabled without an outdoor sensor; forecast preconditioning enabled without a weather entity; a stale area sensor; an inverted comfort band (cool edge below heat edge — no neutral zone, so the home would run constantly); no usable temperature source for any managed device; and a control cycle that keeps failing (`CONTROL_FAILURE_ISSUE_THRESHOLD` consecutive failures — the per-cycle `try/except` is deliberate resilience, and the repair keeps repeated failure from hiding in the log; cleared by the next clean cycle). Learned/transient state — MPC controllers, the adaptive-bias integral, the running-mean outdoor temperature, and the per-device demand latch — is persisted across restarts (the rolling runtime/cycle samples are transient and reset on restart).

All tunables persist (RestoreNumber/RestoreEntity) and re-run control on change. The **whole-home `climate` entity also restores its mode, preset, and manual band** across restarts (`RestoreEntity`) — a restart no longer silently turns the system off. Config flow only handles what *must* be static: the TRVs/ACs, optional outdoor sensor, optional weather entity, and the optional whole-home average override sensors (§4.2).

**Numbers also include** the six editable per-preset edges (`preset_{away,home,sleep}_{heat,cool}`), and one **per-area band offset** (`area_offset_<area_id>`, °C, range ±`AREA_BAND_OFFSET_LIMIT`) created for each area that contains a managed device. A positive offset shifts that area's whole band up — the room runs warmer (heats sooner, releases later); negative runs it cooler. It's applied in the engine by subtracting the offset from the area's *local* effective reading only (clamped to `[MIN_TEMP, MAX_TEMP]`), never the home average — so it biases just that room without distorting the whole-home OR-trigger (§5.2). The set of area entities is fixed at setup; moving a device to a new area needs a reload. **Window detection** is wired from area `binary_sensor`s. The **TRV calibration mode** select carries no entity category, so it appears under the device's *Controls* section.

**Not yet built (future):** a configurable `keepalive_interval` (the cycle interval is currently the fixed `UPDATE_INTERVAL_SECONDS`). Everything else once listed here is now implemented — per-TRV learned MPC params, the per-device valve-% / action / runtime / cycles sensors, and the dedicated `window_open`/`frost_active`/`dew_point_active` binary sensors all exist (§8), as does self-tuning AC bias (§6.2).

---

## 9. MPC specification (with the discussed improvements)

Model: linear room thermal dynamics `dT/dt = gain·u − loss·(T − T_out_or_amb) + solar`, with `u` ∈ [0,1] the valve fraction.

1. **System identification** — replace ad-hoc EMA inference with `scipy.optimize.least_squares` fitting `(gain, loss, solar)` over a rolling window of `(t, T, u, T_out)` samples, with bounds and L2 regularisation toward priors. Produces parameter estimates plus residual diagnostics.
2. **State observer** — a small in-house scalar Kalman filter (`control/mpc/observer.py`), wired into `MpcController.observe()`: each observation projects the previous estimate across the just-elapsed transition (the *previous* valve/outdoor held for `dt`) and corrects with the new measurement. The optimiser plans from the filtered `estimated_temperature`; system identification deliberately consumes **raw** transitions (fitting the model to its own smoothed output would be circular). `Q/R` are fixed (`PROCESS_VAR`/`MEASUREMENT_VAR`) but tunable later; the state persists with the controller and old stores without it load cleanly. Numerical hardening: the fit runs inside physical bounds (`MAX_GAIN`/`MAX_LOSS`) and keeps the prior on solver failure or non-finite output; the Kalman variance is ceilinged (`MAX_VARIANCE`); non-finite observations are ignored and gaps longer than `MAX_SAMPLE_DT_MIN` re-anchor the estimate instead of being learned from; restored state is validated (non-finite params rejected, bad samples dropped, variance capped); and the computed valve % is always clamped to [0, 100].
3. **Optimizer** — replace the hand-rolled coarse/fine grid search with `scipy.optimize.minimize` (`method="SLSQP"` or bounded L-BFGS-B) minimising a quadratic tracking cost over a receding horizon (default 30 min / 6 steps) with control-effort and slew penalties. Bounds `0 ≤ u ≤ max_opening`.
4. **Multi-TRV distribution** — one room/zone-level command distributed to individual TRVs with per-valve deficit compensation (keep BT's idea, cleaner implementation).
5. **Persistence** — learned parameters and observer state saved via a coordinator `Store`, restored on startup; safe cold-start priors.

**Dependency:** `scipy` added to `manifest.json` `requirements`. Heavier wheel but justified; this is the single biggest quality lever. `numpy` is already present in HA core. (`do-mpc`/`cvxpy` considered and rejected for v1 as too heavy.)

Each numerical piece is a **pure, separately unit-tested function** fed synthetic thermal simulations, so the controller is testable without hardware.

---

## 10. Repository layout

```
climate_orchestrator/
├── custom_components/
│   └── climate_orchestrator/
│       ├── __init__.py            # setup, coordinator wiring, platform forwarding, services
│       ├── manifest.json
│       ├── const.py               # domain, defaults, presets, tuning constants
│       ├── models.py              # SmartClimateData, DeviceReading, Band, Status (pure value objects)
│       ├── config_flow.py         # config + options flow (TRVs/ACs, outdoor sensor, weather entity, hints)
│       ├── brand/                 # in-integration icon.png/icon@2x.png (HA >= 2026.3 local brands)
│       ├── coordinator.py         # SmartClimateCoordinator: snapshot + control cycle + persistence
│       ├── settings.py            # NumberSetting/SwitchSetting registries + RuntimeSettings resolver
│       ├── entity.py              # shared base entity + hub DeviceInfo
│       ├── diagnostics.py         # downloadable diagnostics dump
│       ├── control/
│       │   ├── engine.py          # arbitration: guards + capability gating + per-area offset (pure)
│       │   ├── hysteresis.py      # OR-engage / AND-release demand law (pure)
│       │   ├── comfort.py         # apparent temperature + dew point (pure)
│       │   ├── adaptive_comfort.py# running-mean outdoor + saturating cool-edge relaxation (pure)
│       │   ├── adaptive_bias.py   # self-tuning AC setpoint bias (integral feedback) (pure)
│       │   ├── window.py          # window-open suppression + grace debounce (pure)
│       │   ├── slope.py           # least-squares home temperature slope (pure)
│       │   ├── throttle.py        # AC setpoint write throttling (pure)
│       │   ├── forecast.py        # hourly→per-step forecast expansion for preconditioning (pure)
│       │   ├── numeric.py         # shared clamp() helper (pure)
│       │   ├── runtime_stats.py   # runtime-fraction + cycles/hour integrals (pure)
│       │   └── mpc/
│       │       ├── model.py       # first-order thermal model + system ID (scipy)
│       │       ├── observer.py    # Kalman state estimate
│       │       ├── optimizer.py   # receding-horizon valve solve; scalar or forecast series (scipy)
│       │       └── controller.py  # stateful per-room MPC (observe + optimise + persist)
│       ├── sensing/
│       │   ├── registry.py        # area matching, snapshot build, staleness guard
│       │   └── aggregate.py       # mean-or-none / slope helpers (pure)
│       ├── devices/
│       │   ├── adapter.py         # ClimateAdapter: capabilities + read/apply over HA climate services
│       │   ├── model.py           # DeviceCommand / Mode / AdapterCapabilities (pure)
│       │   ├── command.py         # decision → device command (pure)
│       │   ├── reconcile.py       # step-diff command minimisation (pure)
│       │   └── trv.py             # TRV number discovery + local-offset helpers
│       ├── climate.py             # the single whole-home ClimateEntity
│       ├── sensor.py / binary_sensor.py / switch.py / number.py / select.py
│       ├── icons.json / strings.json
│       └── translations/en.json
├── tests/                         # unit/ (mirrors the package) + ha/ (hass fixtures) — see §12
├── pyproject.toml                 # uv-managed, ruff + mypy + pytest config
├── .github/workflows/ci.yml       # ruff, mypy, pytest+coverage, hassfest, HACS (GitHub Actions)
├── .github/workflows/release.yml  # python-semantic-release on green CI
├── hacs.json
├── CHANGELOG.md
└── README.md
```

---

## 11. Tooling

| Concern | Choice | Notes |
|---------|--------|-------|
| Env/deps | **uv** | Fast, lockfile, `uv run` for tasks. |
| Lint + format | **ruff** | Replaces black + flake8 + isort; format + lint in one. |
| Types | **mypy** (strict-ish) | pyright optional in editor. |
| Tests | **pytest** + **pytest-homeassistant-custom-component** | The standard HA harness: `hass` fixture, config-entry/flow helpers, service mocking. |
| Snapshots | **syrupy** | Entity-state and diagnostics snapshot tests. |
| Coverage | **pytest-cov** | Target ≥ 95% line + branch on `control/`, `sensors/`, `devices/`; gate in CI. |
| Hooks | **pre-commit** | ruff + mypy + end-of-file/whitespace. |
| CI | **GitHub Actions** (`.github/workflows/ci.yml`) | Installs uv + Python 3.14 via `astral-sh/setup-uv`; jobs for ruff lint+format, mypy, pytest with coverage + JUnit results (Codecov coverage and Test Analytics uploads), plus hassfest and HACS validation. CI pytest runs with `--timeout=120` (pytest-timeout; CI-only flag, like coverage) and `HYPOTHESIS_PROFILE=ci` (no deadline — loaded-runner deadline flake protection; profile registered in `tests/conftest.py`). A `codecov.yml` splits coverage into components (control / devices / sensing / shell) for visibility; the hard 95% gate stays in pytest. A weekly `links.yml` workflow runs lychee over README/DESIGN/CHANGELOG. `__init__.async_migrate_entry` scaffolds config-entry migration (`CONFIG_ENTRY_VERSION`, refuses future-version downgrades). `custom_components/climate_orchestrator/quality_scale.yaml` tracks the HA integration quality scale honestly (45 done / 7 exempt; no remaining todos). All third-party actions are pinned by commit SHA with version comments (Dependabot keeps them current); `zizmor` lints the workflows themselves in CI, with the few accepted findings suppressed inline with rationale (release's `workflow_run` trigger + credential persistence for the PSR push, and the unpinnable `hassfest@master`/`hacs@main` branches). The release job additionally guards on `head_repository == github.repository`. |
| HA validation | **hassfest** + **HACS action** | `home-assistant/actions/hassfest` validates the manifest/structure; `hacs/action` validates HACS packaging. hassfest validates `strings.json`, which is kept byte-identical to `translations/en.json` (sync-checked in CI and pre-commit); advisory until one green run confirms, then it becomes a gate. |

### 11a. Continuous integration (GitHub Actions)

CI is GitHub Actions (`.github/workflows/ci.yml`), which also unlocks HACS distribution. Jobs:

- **lint-and-test** — `uv sync --dev`, then `uv run ruff check .`, `uv run ruff format --check .`, `uv run mypy custom_components/climate_orchestrator`, and `uv run pytest --cov-report=xml --junitxml=junit.xml`; coverage goes to Codecov, and the JUnit file feeds **Codecov Test Analytics** (per-test run times, failure rates, flake detection — uploaded with `report_type: test_results`, even when pytest fails, since failure data is the point).
- **hassfest** — `home-assistant/actions/hassfest` (advisory via `continue-on-error` until one green run with the synced `strings.json` is confirmed).
- **hacs** — `hacs/action` with `category: integration` (`ignore: brands` stays: that check looks for the domain in `home-assistant/brands`, while since HA 2026.3 the icons ship *inside* the integration — `custom_components/climate_orchestrator/brand/icon.png` + `icon@2x.png`, served via the local brands proxy API and taking priority over the CDN; the SVG source stays in the repo-root `brand/`).

uv (with Python 3.14, HA's runtime) is installed via `astral-sh/setup-uv`.

### 11c. Releases (semantic-release)

Versioning is automated with **python-semantic-release** driven by Conventional Commits (`feat:` → minor, `fix:` → patch, `feat!:`/`BREAKING CHANGE:` → major). The version is the single tag; `[tool.semantic_release]` keeps both `pyproject.toml` (`version_toml`) and `custom_components/climate_orchestrator/manifest.json` (`version_variables`) in lock-step with it.

Prereleases are **branch-based** (PSR's native model — it releases from the branch it runs on). `[tool.semantic_release.branches]` marks `main` as stable and any `feat/*` or `fix/*` branch as prerelease (`prerelease_token = "rc"`). A single workflow handles both:

- **`release.yml`** — triggered by a *successful* CI run on `main`, `feat/**`, or `fix/**` (`workflow_run`), so we never tag a red commit. It checks out whichever branch CI ran on and runs PSR, which reads the branch config to decide stable vs prerelease, bumps `pyproject.toml` + `manifest.json`, updates `CHANGELOG.md`, runs `build_command` to produce `dist/climate_orchestrator.zip` (the integration directory's contents, manifest at the zip root), commits (`chore(release): … [skip ci]`), tags, publishes the GitHub Release, and attaches the zip (`[tool.semantic_release.publish]`). HACS installs that exact asset (`zip_release` + `filename` in `hacs.json`), and `actions/attest-build-provenance` records verifiable provenance for it (`gh attestation verify climate_orchestrator.zip -R <repo>`).
  - Push to a **`feat/*` / `fix/*`** branch → `X.Y.Z-rc.N` prerelease (testers enable *Show beta versions* in HACS).
  - Merge that branch into **`main`** → the stable `X.Y.Z` release HACS serves by default.

Two consequences of feature-branch prereleases: PSR commits the version bump + tag *onto the feature branch* (the `[skip ci]` in the commit message stops a re-trigger loop), and the **version is PEP 440** (`rcN`), so the branch name can't appear in it. One-time bootstrap: tag the current commit `v0.11.0` so PSR continues from that baseline rather than recomputing from zero.

Targeting Python 3.12+ (HA's runtime), with current best practices enforced by ruff + mypy in CI:

- **Type hints everywhere** — fully annotated public and internal APIs; `from __future__ import annotations`; `mypy` in strict-ish mode (`disallow_untyped_defs`, `warn_return_any`). No `Any` without justification.
- **Dataclasses & immutability** — `@dataclass(frozen=True, slots=True)` for value objects (`SmartClimateData`, `DeviceReading`, `Band`, `DeviceState`, `DeviceCommand`, `AdapterCapabilities`, `Writes`, `DeviceInput`/`GlobalInput`/`DeviceDecision`, `Sample`/`ThermalParams`/`KalmanState`). Frozen by default; mutable runtime state lives only in the coordinator.
- **Enums over magic strings** — `StrEnum` for `Demand`, `DeviceKind`, `Mode`, and `Status`; calibration modes and other fixed strings are named constants in `const.py`, never inline literals.
- **Capability-aware adapter** — a single concrete `ClimateAdapter` wraps any HA `climate` entity, reading its `AdapterCapabilities` (can-heat/cool/dry, min/max, step) and translating a pure `DeviceCommand` into the right services; pure logic stays out of it and it's easy to drive with mocked services in tests.
- **Pure functions for logic** — control math (apparent temperature, dew point, hysteresis transitions, MPC steps) is side-effect-free and dependency-injected, keeping I/O at the edges (coordinator/adapter).
- **Modern syntax** — `X | None` unions (PEP 604), `match` where it clarifies, `pathlib`, f-strings, comprehensions over manual loops, `functools.cached_property` where apt.
- **Async correctness** — no blocking calls in the event loop; `async`/`await` throughout; `asyncio.gather` for parallel device commands; HA's `async_*` APIs only.
- **Errors & logging** — narrow exception handling (no bare `except`), typed custom exceptions, structured `_LOGGER` messages with lazy `%` formatting.
- **Docstrings** on modules and public callables; self-documenting names elsewhere. Ruff rules: pycodestyle, pyflakes, isort, pyupgrade, flake8-bugbear, comprehensions, simplify, and async checks.

## 12. Test plan (test-first)

**Layout.** `tests/unit/` mirrors the package (`control/`, `control/mpc/`, `devices/`, `sensing/`) and holds every pure test, including the cross-module property/regression/snapshot suites; `tests/ha/` holds the hass-fixture tests, with the Home Assistant fixtures scoped to `tests/ha/conftest.py` (the root `tests/conftest.py` carries only shared constants, and the engine-input builders shared by the engine/property/regression suites live in `tests/unit/control/builders.py`); the hass-side setup helpers (TRV-with-number registry setup, desired-state and calibration-mode drivers) live in `tests/ha/helpers.py`. Mutation testing targets `tests/unit/` alone (`[tool.mutmut] tests_dir`), since those are the tests that kill `control/` mutants.

- **Pure-function unit tests** (no HA): comfort index & dew point against reference tables; hysteresis state machine across engage/release/edge sequences; sensor aggregation & fallbacks; MPC sysid/observer/optimizer on synthetic first-order thermal simulations (assert convergence, stability, no windup, bounds respected).
- **Control-engine tests:** arbitration priority (frost > window > outdoor gating > demand), heat/cool mutual-exclusion invariant, deadband early-out, the worked example from requirements (home avg > 25 OR living room > 25 engages AC; stays on until both ≤ target or room near heat band).
- **Adapter tests:** the `ClimateAdapter` issues the correct services for TRV valve %, TRV offset, and AC setpoint + mode over a generic HA `climate` entity, honouring `AdapterCapabilities` (capability gating, range/step clamping) with mocked services.
- **Integration tests (hass fixture):** config flow (device + sensor selection, overrides), entity creation snapshots, options/runtime entity changes re-trigger control, restart restores learned MPC + preset state.
- **Resilience tests (§6.4):** a TRV or AC going `unavailable` excludes only that device while the home entity stays available and controls the rest; an offline sensor drops out of the home/area average; an area with an offline configured sensor falls back to the home average; one device raising an exception/timeout never aborts the cycle for the others; absent-device learned state is retained across the dropout.
- **Regression fixtures:** recorded sensor traces replayed through the control engine (`control/engine.py`) to catch behavioural drift, plus **syrupy snapshots** (`tests/unit/test_snapshot_regression.py`, `tests/unit/snapshots/`) pinning the exact comfort-curve and adaptive-cooling-comfort outputs — regenerate intentionally with `pytest --snapshot-update`.
- **Mutation testing** (`mutmut`, scoped to `control/` via `[tool.mutmut]`): line/branch coverage and Hypothesis invariants don't prove the *math* is right — a flipped sign or mis-scaled `dt` in the thermal model, optimizer, or comfort curves can still pass. `uv run mutmut run` mutates the pure control modules and surfaces any mutant the suite fails to kill; run it in the HA dev env (Python 3.14).

A subagent-driven verification pass reviews coverage gaps before sign-off.

---

## 13. Persistence and restore

Coordinator-owned `Store` (versioned) holds: learned MPC parameters/observer state per device, preset values, latched demand/hysteresis state, and the self-tuning AC bias. Restored on startup with safe priors; schema-migrated on version bumps. Fire-and-forget work (debounced refreshes, store saves, auto valve maintenance) is spawned exclusively via the coordinator's `_background()` helper — `ConfigEntry.async_create_background_task` — so every task is tracked by the entry and cancelled on unload; nothing outlives the coordinator. Runtime state is bounded: store restore filters to currently-managed entities (a removed device's keys would otherwise cycle store→runtime→store forever), per-area window timers are pruned each cycle against the live snapshot, the hourly forecast cache is capped (`_FORECAST_MAX_HOURS`), and the slope sample deque has a hard `maxlen`. Store writes are flash-wear-aware: learned state (MPC history, rmot EMA, bias integrals) moves continuously, so per-cycle delay-saves would mean a write every ~90 s forever on SD-card boxes — `_maybe_persist()` schedules a save at most every `_PERSIST_INTERVAL` (15 min) and only when the payload actually changed; unload/shutdown flushes whatever the limiter was holding back.

---

*Living document — reflects the current implementation.*
