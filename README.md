# Climate Orchestrator

[![CI](https://github.com/alawresz/climate_orchestrator/actions/workflows/ci.yml/badge.svg)](https://github.com/alawresz/climate_orchestrator/actions/workflows/ci.yml)
[![Release](https://img.shields.io/github/v/release/alawresz/climate_orchestrator?include_prereleases&sort=semver)](https://github.com/alawresz/climate_orchestrator/releases)
[![codecov](https://codecov.io/gh/alawresz/climate_orchestrator/graph/badge.svg)](https://codecov.io/gh/alawresz/climate_orchestrator)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![License: MIT](https://img.shields.io/github/license/alawresz/climate_orchestrator)](./LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

One thermostat for the whole house. Instead of controlling each radiator valve
and air conditioner separately, you set a comfortable temperature range once and
Climate Orchestrator drives every device to keep each room inside it — heating cold
rooms, cooling hot ones, and preventing the two from fighting.

Each device follows the temperature sensor in its *own* Home Assistant area while
also watching the whole-home average, so one hot room can call in the AC even
when the rest of the house is fine. It controls off a humidity-adjusted
"feels-like" temperature, backs off for open windows and mild outdoor weather,
protects against frost, and — where radiator valves support it — can learn each
room's thermal behaviour to heat it more precisely over time.

You control it through a single `climate.climate_orchestrator` entity plus a set of live
toggles and numbers; there's no YAML to write. This README covers what it does
and what every control is for. For the architecture and the maths, see
[`DESIGN.md`](./DESIGN.md).

## What it does

- **One control surface.** A single `climate.climate_orchestrator` entity with two
  setpoints (a heating edge and a cooling edge) controls all your TRVs and ACs.
- **Area-matched sensors.** Each device reads the temperature/humidity sensor on
  its Home Assistant **area** (Settings → Areas → *Related sensors*); a home-wide
  average is computed across all of them.
- **Asymmetric trigger.** A device engages when *its area OR the home average*
  crosses an edge, and disengages only when *both* are back at target.
- **Comfort index.** Control runs off a humidity-adjusted "feels-like" (apparent)
  temperature, with a dew-point guard that can run the AC's dry mode.
- **Coordinated heat/cool.** A neutral band between the two setpoints keeps
  heating and cooling from fighting; frost protection, window-open, and
  outdoor-temp gating are layered guards.
- **AC offset.** ACs are commanded a setpoint biased below the real target so the
  AC's own sensor doesn't satisfy before the room does. Fan/swing controls are
  surfaced and forwarded when the AC supports them.
- **MPC calibration (opt-in).** TRVs can be driven by an MPC valve controller or
  a local-temperature offset; learned thermal parameters persist across restarts.
- **Resilient.** One device or sensor going offline never takes the whole-home
  entity down.

## Requirements

- Home Assistant `2024.12` or newer.
- `scipy` (declared in the manifest; Home Assistant installs it automatically on
  first setup).
- Each managed device's **HA area** should have a temperature (and ideally
  humidity) sensor assigned under *Related sensors*; otherwise that device falls
  back to the home-wide average.

## Installation

### Via HACS (recommended)

[![Open your Home Assistant instance and add this repository to HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=alawresz&repository=climate_orchestrator&category=integration)

1. Click the button above (it opens HACS with this repository pre-filled), or add
   it manually in HACS → **⋮ → Custom repositories**:
   `https://github.com/alawresz/climate_orchestrator`, category **Integration**.
2. Search for **Climate Orchestrator** in HACS, download it, then **fully
   restart** Home Assistant.
3. **Settings → Devices & Services → Add Integration → "Climate Orchestrator"**.

### Manual

1. Copy `custom_components/climate_orchestrator/` into your Home Assistant
   configuration's `custom_components/` directory:

   ```
   <config>/custom_components/climate_orchestrator/
   ```

2. **Fully restart** Home Assistant (a new integration is only discovered on
   startup; "reload" is not enough). On first start HA installs `scipy`.
3. **Settings → Devices & Services → Add Integration → "Climate Orchestrator"**, then
   select your TRVs, ACs, and (optionally) an outdoor sensor and weather entity.

You can change the selected devices later via the integration's **Configure**
(options) dialog. The same dialog has two advanced fields — **TRV valve-opening**
and **local-calibration number name hints** — used to auto-discover those
`number` entities on a TRV for `mpc`/`offset` modes. They default to Zigbee2MQTT
naming; if you add a TRV from another brand whose entities are named differently,
add its naming here (comma-separated) so MPC/offset can find them.

## Entities created

A single hub device exposes:

| Entity | Purpose |
|--------|---------|
| `climate.climate_orchestrator` | Whole-home control: preset, mode, fan/swing (if the AC supports it). Two setpoints with both TRVs + an AC; a single setpoint (heat-only or cool-only) when only one device kind is configured. |
| `sensor.*_home_average_temperature` / `_humidity` | Home-wide aggregates. |
| `sensor.*_home_feels_like_temperature` | Humidity-adjusted apparent temperature of the home. |
| `sensor.*_temperature_slope` | Home temperature rate of change (K/min). |
| `sensor.*_adaptive_cool_setpoint` | The cool edge after the adaptive cooling-comfort shift (the heat edge never moves). |
| `sensor.*_running_mean_outdoor_temperature` | Running-mean outdoor temperature driving adaptive comfort (diagnostic). |
| `sensor.*_<trv>_mpc_*` | Per-TRV MPC diagnostics: heating power, heat loss, learning status, model error (diagnostic). |
| `sensor.*_<device>_*` | Per-device diagnostics: action (+ last command), runtime %, cycles/hour, valve % (TRV) (diagnostic). |
| `sensor.*_hvac_action_reason` | Why it's heating/cooling/idle, with per-device reasons (diagnostic). |
| `sensor.*_status` | `initializing` / `ok` / `degraded`, with offline devices in `unavailable_devices` (diagnostic). |
| `binary_sensor.*_window_open` / `_frost_active` / `_dew_point_active` | Operational state for dashboards/automations. |
| `select.*_calibration_mode` | `target` (default) / `mpc` / `offset`. |
| `switch.*` | The feature toggles (see *Controls & settings reference*). |
| `number.*` | The tuning numbers, per-preset band edges, and a per-area band offset (see *Controls & settings reference*). |

All tunables persist across restarts and re-run control when changed.

## How it works (the control loop)

### Two setpoints, not one

A normal thermostat has a single target and flips a heater on and off around it.
Climate Orchestrator uses a **band** with two edges:

- a **heat setpoint** — the bottom of the band; drop below it and heating engages.
- a **cool setpoint** — the top of the band; rise above it and cooling engages.

Between the two is a **neutral zone** where nothing runs. That gap keeps the
radiators and the AC from fighting (one heating while the other cools the same
air), so you can leave both heating and cooling armed all year and the system
does whichever the room needs, or nothing. Each preset (Home / Away / Sleep) is a
pair of these setpoints, editable live.

If you've configured only one kind of device the thermostat adapts: TRVs with no
AC become a plain **heat / off** thermostat with a single setpoint, and an AC
with no TRVs becomes **cool / off** — no inert second handle. (Turning on **AC
heating assist** makes an AC count as heat-capable, so an AC-only setup then
presents the full heat/cool band — a reversible heat pump.)

### Two temperatures, asymmetric trigger

For each device, Climate Orchestrator looks at two temperatures: the device's *own room*
and the *whole-home average*.

- **To start:** *either* temperature crossing an edge is enough. A cold bedroom
  turns on its own radiator; a house that's warm on average can switch on the AC
  in a room that's only borderline.
- **To stop:** *both* have to be back at target before the device backs off.

This "eager on, reluctant off" asymmetry prevents short-cycling on small sensor
fluctuations.

### Where it aims

When heating, Climate Orchestrator drives to **just past the heat setpoint** — the heat
setpoint plus the **Switching tolerance** (0.3 °C by default) — and stops.
Cooling mirrors it: down to just past the cool setpoint. Rooms settle at the
efficient end of the band: the cool end in winter, the warm end in summer. The
small overshoot past the edge also gives the anti-short-cycling its margin.

### Feels-like, not just the number (Comfort index)

With **Comfort index targeting** on (default), the room and home temperatures are
converted to a humidity-adjusted "feels-like" (apparent) temperature before they
meet the band, so a muggy room is treated as warmer than the bare number. Cooling
then engages a little earlier in humid weather and a little later in dry weather.
**Comfort humidity influence** scales how strongly humidity counts (`0` = ignore
it, `1` = full feels-like, `>1` = amplify). A separate **dew-point guard** can put
the AC in dry mode when humidity is high.

### Relaxing the cooling when it's hot out (Adaptive cooling comfort)

With **Adaptive cooling comfort** on (optional, off by default), the **cool setpoint, and
only the cool setpoint**, relaxes upward once it's hotter outside than you'd cool
for anyway. It tracks a slow running mean of the outdoor temperature:

```
onset      = cool setpoint + bias
excess     = max(0, running-mean-outdoor − onset)
cool shift = max shift × (1 − exp(−excess / response))
```

The cool edge stays at your preset until the running-mean outdoor passes the
**onset**, then eases upward by a smooth, saturating amount — gently at first,
ever more slowly, approaching but never reaching the **max shift** cap. The heat
setpoint is never touched. Three numbers shape the curve: **max shift** (the cap),
**onset bias** (how much hotter than the cool setpoint it must be before relaxing
starts), and **response** (how gently it ramps).

With a Home preset of 20.5/24.5 and the defaults (onset 25.5°):

| Running-mean outdoor | Cool setpoint |
|---------------------:|:-------------:|
| ≤ 22° | 24.5° (no shift) |
| 28° | ~25.5° |
| 33° | ~26.1° |
| 45° | ~26.5° |

The adjusted band is *always computed* (the **Adaptive heat/cool setpoint**
sensors preview it even when the toggle is off) but only *applied* when the toggle
is on, which requires an outdoor sensor.

### Safety guards

Layered over the decision, highest priority first: **frost protection** (force
heat if a room is freezing — overrides everything, even an open window) →
**window open** (a window/door open in a room stops that room's heating/cooling,
after an optional grace delay — though a portable AC can ignore *its own* room's
vent window via **AC ignores open windows**, while still stopping for a window
open in another room) → device capability (a radiator can't cool; an AC
only heats if allowed) → **outdoor gating** (don't heat when it's mild out or cool
when it's cool out).

### Each cycle, step by step

Climate Orchestrator re-evaluates whenever a relevant sensor changes (plus a periodic
safety check). For every managed device:

1. **Read the room** — the device's area temperature/humidity and the home
   average, as feels-like values when Comfort index targeting is on. An area
   sensor that has stopped reporting (older than the **Sensor staleness
   timeout**) is treated as missing and the home average is used instead.
2. **Place it against the band**, after any adaptive-comfort shift: below the heat
   setpoint → wants heat; above the cool setpoint → wants cooling; between →
   content.
3. **Decide, with memory** — apply the eager-on / reluctant-off rule, remembering
   what the device was already doing, and settle on heat, cool, or idle.
4. **Run the safety guards** — any can override the decision (order above).
5. **Send the smallest possible command** — anything that wouldn't change the
   device is skipped, to keep the radios quiet and the logs clean.

### A worked example

Home preset, heat 20.5° / cool 24.5°. The living room reads 23.8°, but it's
humid, so the comfort index treats it as ~24.8° — over the cool edge. The AC
engages and is commanded a setpoint below the cool target (so the *room*, not the
AC's own sensor, reaches target). A quiet bedroom at 24.1° is below its own cool
edge, but the high home average pulls it in too. As rooms drop back past the cool
target they release one by one. No radiator runs, because every room is well above
the 20.5° heat edge. If a window were open in the bedroom it would sit out the
cycle (after any grace delay); if it were already mild outside, the AC wouldn't
engage at all.

## Under the hood: how the hardware is driven

The control loop decides *whether* each device should heat or cool. This section
covers *how* that intent becomes commands, which differs for radiator valves and
air conditioners.

### Driving the radiators (TRV calibration modes)

A TRV's built-in sensor sits on the hot radiator and reads warmer than the room,
so left alone it closes the valve before the room is warm. The **TRV calibration
mode** select chooses how Climate Orchestrator handles that:

- **`target` (default, safe).** The TRV is told to heat to the band's heat target
  (`heat setpoint + tolerance`), trusting the TRV's own loop. Always works, but
  inherits the TRV's sensor bias. The recommended starting point.
- **`offset`.** Climate Orchestrator writes the TRV's `local_temperature_calibration`
  with `(room sensor − TRV's own reading)`, so the TRV's internal loop regulates
  to the **room** temperature instead of the air next to the radiator.
- **`mpc` (Model Predictive Control).** Climate Orchestrator learns each room and drives
  the valve opening directly:

  1. **Thermal model per room** — first-order: `temperature change per minute =
     gain × valve − loss × (room − outdoor)`. `gain` is how fast a fully-open
     valve heats the room (K/min); `loss` is how fast it leaks heat (per minute).
  2. **Learning (system identification)** — fits `gain` and `loss` from observed
     `(valve, temperature change, outdoor)` samples with a least-squares solver
     (SciPy), regularised toward sane priors. After ~6 samples it moves from
     **learning** to **ready**; the fitted values show as the **MPC heating
     power** / **MPC heat loss** diagnostics and persist across restarts.
  3. **A Kalman filter** smooths the noisy, slow-reporting sensor between updates.
  4. **Receding-horizon optimisation** — simulates the room a few steps ahead
     under the learned model and writes the **valve opening percentage** that best
     reaches the heat target, easing off before overshooting. When the room no
     longer needs heat, the valve is driven **fully closed** rather than left at
     its last opening (a common cause of a TRV that "stays open" and keeps
     heating).

  If a TRV doesn't expose the `valve_opening_degree` /
  `local_temperature_calibration` numbers (Zigbee2MQTT naming by default, but the
  discovery hints are configurable in the options dialog for other brands),
  `mpc`/`offset` can't act and the device falls back to `target` safely. Validate
  on your hardware before trusting it on the radiators.

### Driving the air conditioner

An AC is driven purely through its **setpoint** (Climate Orchestrator never fakes its
sensor). Two facts shape the logic: its internal sensor reads cooler than the
room, and it only runs the compressor when its setpoint is below what that sensor
reads. So when cooling is wanted, the commanded setpoint is the lower of:

1. **Room-referenced:** `cool target − bias`. The **AC cooling setpoint bias**
   pushes below the real target so the AC's sensor doesn't satisfy before the
   room. With **Self-tuning AC bias** on (default), an integral controller grows the
   bias (up to **Max AC cooling setpoint bias**) while the room stays above target
   and cools too slowly, then decays it back once satisfied.
2. **Compressor-referenced (proportional):** below the AC's *own* reported
   temperature by `max(how far the room is above target, 1 °C)`, so the compressor
   always runs and harder when the room is further over target.

Whichever is lower wins, clamped to the AC's accepted range and snapped to its
step. The room sensor (via the engine releasing the demand) is what stops it. If
the dew point is high the AC can run **dry** mode instead, and any fan/swing modes
it supports are surfaced on the whole-home entity and forwarded.

Because that anchored setpoint drifts a little every cycle, the commanded value
is **throttled**: it's only re-sent when it moves at least 0.5 °C *and* a few
minutes have passed, with a periodic keep-alive re-assert. This keeps a steady
cooling run from spamming the AC with near-identical setpoint changes.

## Controls & settings reference

Every item below is a runtime entity on the hub device — adjust any of it live; it
persists and re-runs control immediately.

### TRV calibration mode (`select`)

| Control | Default | Description |
|---------|---------|-------------|
| TRV calibration mode | `target` | How radiator valves are driven. `target`: HVAC mode + setpoint (safe). `mpc`: a learned model writes the valve opening. `offset`: corrects the TRV's own sensor so it heats to the room. `mpc`/`offset` need the TRV's valve/calibration numbers, else falls back to `target`. |

### Comfort presets (`number`)

Selecting a preset on the thermostat applies its two edges; editing the active
preset's number moves the live setpoint at once. Heating runs below the heat
setpoint, cooling above the cool setpoint, nothing between. Each edge is editable
within 7–35 °C.

| Preset | Heat setpoint | Cool setpoint |
|--------|:-------------:|:-------------:|
| Away | 16.0 °C | 30.0 °C |
| Home (default) | 20.5 °C | 24.5 °C |
| Sleep | 19.5 °C | 23.5 °C |

### Feature toggles (`switch`)

| Switch | Default | Description |
|--------|---------|-------------|
| Comfort index targeting | On | Control off a humidity-adjusted feels-like (apparent) temperature rather than dry-bulb. While on, the climate entity's current temperature shows the feels-like value (raw dry-bulb kept in the `dry_bulb_temperature` attribute). How strongly humidity counts is set by **Comfort humidity influence**. |
| Dew point guard | On | When a room's dew point exceeds the **Dew point threshold** and the AC isn't already cooling, run the AC in **dry** mode to dehumidify. |
| Window open detection | On | A window/door `binary_sensor` open in a device's area stops that device (after **Window open delay**). Auto-discovered from the area. Frost protection still overrides it. |
| AC ignores open windows | Off | Let **coolers** ignore a window open in their *own* room — for a portable/exhaust-hose split that *needs* its window open to vent. The AC still stops if a window is open in *another* room, and heaters always stop. Only matters when Window open detection is on. |
| Outdoor temperature gating | On | Suppress heating when it's mild out (≥ **Heating off above outdoor temperature**) and cooling when it's cool out (≤ **Cooling off below outdoor temperature**). Needs an outdoor sensor. |
| Frost protection | On | Force heat in any area below **Frost protection temperature**, overriding mode, preset, and window-open. |
| AC heating assist | Off | Allow an AC that supports `heat` to participate in heating (radiators own heating by default). On an AC-only setup this also turns the thermostat into a full heat/cool one. |
| Self-tuning AC bias | On | Auto-tune the AC cooling setpoint bias with integral feedback (grows up to **Max AC cooling setpoint bias**, decays when satisfied). The **AC cooling setpoint bias** becomes the floor. |
| Adaptive cooling comfort | Off | Relax the cool setpoint upward when it's hot outside (see *Relaxing the cooling when it's hot out*). Needs an outdoor sensor. |
| Automatic valve maintenance | Off | Periodically exercise the TRV valves (full open → closed) every **Valve maintenance interval** days. Skipped while a room is actively heating. |

### Tuning numbers (`number`)

| Number | Default | Range | Description |
|--------|:-------:|:-----:|-------------|
| Heat/cool release offset | 0.5 °C | 0–3 | How far the room must swing back toward the opposite edge before a device stops. Larger = longer runs, fewer cycles. |
| `<area>` band offset | 0 °C | −5–5 | Per-area comfort nudge: a positive value shifts that area's whole band up so the room runs **warmer** (heats sooner, cools later); negative runs it cooler. One number per managed area; biases only that area's local reading, not the home average. |
| Switching tolerance | 0.3 °C | 0–2 | How far past the trigger edge a device drives, which is also the target (`heat setpoint + tolerance`, `cool setpoint − tolerance`, each capped at the band midpoint). |
| Comfort humidity influence | 1.0 | 0–2 | How strongly humidity shifts the comfort index: `effective = dry-bulb + influence × (apparent − dry-bulb)`. `0` ignores humidity (pure dry-bulb), `1` is the full feels-like temperature, `>1` amplifies it. Only matters when Comfort index targeting is on. |
| Dew point threshold | 16 °C | 10–22 | Dew point above which the Dew point guard runs dry mode. |
| Heating off above outdoor temperature | 20 °C | 5–30 | Outdoor cut-off above which heating is suppressed. |
| Cooling off below outdoor temperature | 16 °C | 0–25 | Outdoor cut-off below which cooling is suppressed. |
| Frost protection temperature | 7 °C | 3–12 | Safety floor that forces heat. |
| AC cooling setpoint bias | 1.5 °C | 0–5 | How far below the real target the AC's setpoint is pushed. The floor when Self-tuning AC bias is on. |
| Max AC cooling setpoint bias | 4 °C | 0.5–8 | Ceiling for the adaptive AC bias (anti-windup). |
| Adaptive cooling comfort max shift | 2 °C | 0–5 | The most the cool edge may rise under adaptive cooling comfort; the curve approaches but never exceeds it. |
| Adaptive cooling comfort onset bias | +1 °C | −3–3 | Slides the relaxation onset vs the cool edge. `+1` waits until 1° hotter than the cool setpoint; `−1` starts a degree earlier. |
| Adaptive cooling comfort response | 5 °C | 1–10 | How gently the cool edge ramps — the degrees of outdoor excess for ~63% of the cap. Larger = gentler. |
| Window open delay | 0 min | 0–30 | Grace period an open window may stay open before its area stops. `0` stops immediately. Frost protection ignores it. |
| Valve maintenance interval | 30 days | 1–60 | Days between automatic valve-exercise runs (when Automatic valve maintenance is on). |
| Sensor staleness timeout | 6 h | 0–12 h | Treat an area sensor that hasn't reported for longer than this as missing (falls back to the home average) and raise a repair. `0` disables the guard. |

Every commanded AC setpoint is clamped to the device's own min/max and snapped to
its step, so a large bias can never ask for a temperature the AC won't accept.

### Sensors

| Sensor | Description |
|--------|-------------|
| Home average temperature / humidity | The home-wide aggregates used as the second trigger input (primary measurements). |
| Home feels-like temperature | The home comfort index — apparent temperature of the home average scaled by **Comfort humidity influence** (equals the raw apparent temperature at the default 1.0). What Comfort index targeting judges against. |
| Temperature slope (K/min) | Rate the home average is rising or falling (least-squares over a trailing window). |
| Adaptive cool setpoint | The cool edge after the adaptive cooling-comfort shift (the heat edge never moves). Always computed, so you can preview the effect before enabling it. |

### Diagnostics

| Diagnostic | Description |
|------------|-------------|
| {TRV} MPC heating power / heat loss | The learned `gain` (K/min at full valve) and `loss` (1/min). Populated only in `mpc` mode. |
| {TRV} MPC learning status | `idle` (no model / not in MPC mode), `learning` (collecting samples), or `ready`. |
| {TRV} MPC model error | RMS residual (K) of the learned fit over its history — lower means a better-trusted model. |
| {device} action | The device's current action (idle / heating / cooling / drying / off / unavailable), with the last commanded mode + setpoint as attributes. |
| {device} runtime | Percentage of the last hour the device was running. |
| {device} cycles per hour | Off→on starts per hour over the last hour — surfaces short-cycling. |
| {TRV} valve position | The last commanded valve opening % (in `mpc` mode). |
| Running mean outdoor temperature | The slow exponential running mean of the outdoor temperature driving adaptive comfort. |
| Status (diagnostic) | `initializing` during the post-restart warm-up, then `ok`, or `degraded` once a managed device is unavailable or no temperature source can be found. Any offline devices are listed in its `unavailable_devices` attribute. |
| HVAC action reason | Plain-language headline of why the home is heating/cooling/idle/paused (e.g. `Heating`, `Frost protection`, `Paused — window open`), with a per-device breakdown in its attributes. |

### Binary sensors

| Binary sensor | Description |
|---------------|-------------|
| Window open | On when any managed area reports a window/door open (open areas listed in attributes). |
| Frost protection active | On when any device is in forced frost-protection heating. |
| Dehumidifying | On when an AC is running dry mode for the dew-point guard. |

## Services

Two services for radiator-valve upkeep, callable from automations, scripts, or
Developer Tools → Actions (target the whole-home `climate` entity):

- **`climate_orchestrator.run_valve_maintenance`** — drive the TRV valves fully open then
  closed once, to stop a valve seizing or scaling when held at one position for a
  long time. Optional `trvs:` to scope to specific valves (default: all). The
  **Automatic valve maintenance** switch runs this on a schedule.
- **`climate_orchestrator.reset_mpc_learning`** — forget the learned MPC thermal model
  for some or all TRVs, so they re-learn from scratch. Optional `trvs:` to scope.

## Diagnostics & repairs

- **Download Diagnostics** from the device page (⋮ → *Download diagnostics*) for a
  full JSON dump: merged config, resolved settings, the latest sensor snapshot,
  per-device decisions and reasons, learned MPC parameters, and the adaptive
  state.
- **Repairs:** a notice is raised (and auto-cleared) for silent misconfigurations:
  a TRV in `mpc`/`offset` mode whose `valve_opening_degree` /
  `local_temperature_calibration` number can't be found (falls back to `target`);
  **Adaptive cooling comfort** enabled with no outdoor sensor; an area sensor that has
  gone stale (stopped reporting past the staleness timeout); an inverted comfort
  band (cool setpoint below the heat setpoint, leaving no neutral zone); and no
  usable temperature source for any managed device. The last two (stale sensor,
  no temperature source) are transient right after a Home Assistant restart, so
  while the **Status** sensor reads `initializing` they're held back — they only
  surface once the warm-up window has elapsed and the gap is therefore real.
- Learned state (MPC models, the adaptive bias, the running-mean outdoor
  temperature, and the per-device demand latch) is persisted, so a restart resumes
  where it left off.

## Development

Uses [uv](https://github.com/astral-sh/uv), [ruff](https://docs.astral.sh/ruff/),
[mypy](https://mypy-lang.org/), and [pytest](https://pytest.org/) with
[`pytest-homeassistant-custom-component`](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component).

```bash
uv venv --python 3.13 && uv sync --dev   # create env, install deps
uv run ruff check . && uv run ruff format --check .
uv run mypy custom_components/climate_orchestrator
uv run pytest                            # tests + coverage
```

The repo is laid out as a standalone project (`pyproject.toml`, `.venv`,
`custom_components/`, `tests/`); deploy by copying
`custom_components/climate_orchestrator/` into your HA config (see Installation).

### Releases

Versioning is automated by [python-semantic-release](https://python-semantic-release.readthedocs.io/)
from [Conventional Commits](https://www.conventionalcommits.org/): `fix:` → patch,
`feat:` → minor, `feat!:` / `BREAKING CHANGE:` → major. The version is kept in
lock-step across `pyproject.toml` and the integration `manifest.json`.

Prereleases are branch-based (semantic-release's native model):

- **Push to a `feat/*` or `fix/*` branch** (after CI is green) cuts a
  `X.Y.Z-rc.N` **prerelease** — enable *Show beta versions* on the integration in
  HACS to test it.
- **Merge that branch into `main`** cuts the stable `vX.Y.Z` release HACS serves.

So commit messages drive the version; non-conventional commits (e.g. `chore:`,
`docs:`) don't trigger a release. (Versions are PEP 440, so the branch name
can't appear in the version string itself.)

### Definition of done

Every change ships with its documentation and tests in the same commit. A change
is done only when:

- Behaviour, entities, and settings are reflected in this **README** (especially
  the *Controls & settings reference* and *How it works* sections).
- Architectural or design decisions are reflected in **`DESIGN.md`**.
- It has **tests** (pure unit tests for logic, `pytest-homeassistant-custom-component`
  tests for HA-facing glue), and `ruff` + `pytest` are green.

## Status

Feature-complete against the design (`DESIGN.md`), heavily unit- and
integration-tested. Hardware-specific bits (the TRV valve/offset writes) are
**unvalidated on real devices** — `target` calibration mode is the safe baseline.
This is early software; keep a fallback thermostat until it has proven itself on
your system.

## License

Released under the [MIT License](./LICENSE).
