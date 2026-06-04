# Reference

A single hub device exposes every entity below. All tunables persist across
restarts and re-run control when changed — adjust any of it live.

## Entities at a glance

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
| `switch.*` | The feature toggles (below). |
| `number.*` | The tuning numbers, per-preset band edges, and a per-area band offset (below). |

## Climate entity

`climate.climate_orchestrator` is the whole-home control surface: preset, mode,
fan/swing (if the AC supports it). Two setpoints with both TRVs + an AC; a
single setpoint (heat-only or cool-only) when only one device kind is
configured. While **Comfort index targeting** is on, the climate entity's
current temperature shows the feels-like value (raw dry-bulb kept in the
`dry_bulb_temperature` attribute).

## Select: TRV calibration mode

| Control | Default | Description |
|---------|---------|-------------|
| TRV calibration mode | `target` | How radiator valves are driven. `target`: HVAC mode + setpoint (safe). `mpc`: a learned model writes the valve opening. `offset`: corrects the TRV's own sensor so it heats to the room. `mpc`/`offset` need the TRV's valve/calibration numbers, else falls back to `target`. |

## Numbers: comfort presets

One heat/cool edge pair per preset, each editable within 7–35 °C — behaviour in
[Presets and their edges](../guides/comfort-features.md#presets-and-their-edges).
Only presets selected in the integration's Configure dialog are offered and get
these numbers; the manual band needs no preset.

| Preset | Heat setpoint | Cool setpoint |
|--------|:-------------:|:-------------:|
| Away | 16.0 °C | 30.0 °C |
| Home (default) | 20.5 °C | 24.5 °C |
| Sleep | 19.5 °C | 23.5 °C |

The [boost preset](../guides/comfort-features.md#boost) has no edge pair;
instead it gets two tunables (when selected):

| Number | Default | Range | What it does |
|--------|---------|-------|--------------|
| Boost offset | 2.0 °C | 0.5–5 °C | How far boost pushes the demanded band edge. |
| Boost duration | 30 min | 5–240 min | How long until the boost auto-reverts. |

## Switches: feature toggles

| Switch | Default | Description |
|--------|---------|-------------|
| Home average trigger | On | When off, each room engages and releases on its **own** reading only — the home average no longer pulls borderline rooms in or holds them on. Rooms without their own area sensor still use the home average as their only reading. The averages and their sensors stay available for display/automations. |
| Comfort index targeting | On | Control off a humidity-adjusted feels-like (apparent) temperature rather than dry-bulb. While on, the climate entity's current temperature shows the feels-like value (raw dry-bulb kept in the `dry_bulb_temperature` attribute). How strongly humidity counts is set by **Comfort humidity influence**. |
| Dew point guard | On | When a room's dew point exceeds the **Dew point threshold** and the AC isn't already cooling, run the AC in **dry** mode to dehumidify. |
| Window open detection | On | A window/door `binary_sensor` open in a device's area stops that device (after **Window open delay**). Auto-discovered from the area. Frost protection still overrides it. |
| AC ignores open windows | Off | Let **coolers** ignore a window open in their *own* room — for a portable/exhaust-hose split that *needs* its window open to vent. The AC still stops if a window is open in *another* room, and heaters always stop. Only matters when Window open detection is on. |
| Outdoor temperature gating | On | Suppress heating when it's mild out (≥ **Heating off above outdoor temperature**) and cooling when it's cool out (≤ **Cooling off below outdoor temperature**). Needs an outdoor sensor. |
| Frost protection | On | Force heat in any area below **Frost protection temperature**, overriding mode, preset, and window-open. |
| AC heating assist | Off | Allow an AC that supports `heat` to participate in heating (radiators own heating by default). On an AC-only setup this also turns the thermostat into a full heat/cool one. |
| Self-tuning AC bias | On | Auto-tune the AC cooling setpoint bias with integral feedback (grows up to **Max AC cooling setpoint bias**, decays when satisfied). The **AC cooling setpoint bias** becomes the floor. |
| Adaptive cooling comfort | Off | Relax the cool setpoint upward when it's hot outside (see [Comfort features](../guides/comfort-features.md)). Needs an outdoor sensor. |
| Forecast preconditioning | Off | Feed the weather entity's hourly forecast into the MPC valve optimisation so radiators pre-heat ahead of a cold spell (see [Comfort features](../guides/comfort-features.md)). MPC calibration mode + a weather entity only; can only raise the valve, never under-heat the present. |
| Automatic valve maintenance | Off | Periodically exercise the TRV valves (full open → closed) every **Valve maintenance interval** days. Skipped while a room is actively heating. |

## Numbers: tuning

| Number | Default | Range | Description |
|--------|:-------:|:-----:|-------------|
| Heat/cool release offset | 0.5 °C | 0–3 | How far the room must swing back toward the opposite edge before a device stops. Larger = longer runs, fewer cycles. |
| `<area>` band offset | 0 °C | −5–5 | Per-area comfort nudge: a positive value shifts that area's whole band up so the room runs **warmer** (heats sooner, cools later); negative runs it cooler. One number per managed area; biases only that area's local reading, not the home average. |
| Preconditioning look-ahead | 2 h | 0.5–8 | How far ahead **Forecast preconditioning** plans against the weather forecast. Longer looks further out to pre-heat sooner before a cold spell. |
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
| Sensor staleness timeout | 6 h (the UI shows minutes: 360) | 0–12 h (0–720 min) | Treat an area sensor that hasn't reported for longer than this as missing (falls back to the home average) and raise a repair. `0` disables the guard. |

!!! note
    Every commanded AC setpoint is clamped to the device's own min/max and
    snapped to its step, so a large bias can never ask for a temperature the AC
    won't accept.

## Sensors

| Sensor | Description |
|--------|-------------|
| Home average temperature / humidity | The home-wide aggregates used as the second trigger input (primary measurements). Computed from the managed areas' sensors, or taken from your own override sensors when configured. |
| Home feels-like temperature | The home comfort index — apparent temperature of the home average scaled by **Comfort humidity influence** (equals the raw apparent temperature at the default 1.0). What Comfort index targeting judges against. |
| Temperature slope (K/min) | Rate the home average is rising or falling (least-squares over a trailing window). |
| Adaptive cool setpoint | The cool edge after the adaptive cooling-comfort shift (the heat edge never moves). Always computed, so you can preview the effect before enabling it. |

## Diagnostics

| Diagnostic | Description |
|------------|-------------|
| {TRV} MPC learning status | `idle` (no model / not in MPC mode), `learning` (collecting samples), or `ready`. The learned model rides along as attributes: `heating_gain` (K/min at full valve), `heat_loss` (1/min), `model_error` (RMS residual of the fit, K — lower means a better-trusted model), and `samples`. |
| {device} action | The device's current action (idle / heating / cooling / drying / off / unavailable), with the last commanded mode + setpoint as attributes. |
| {device} runtime | Percentage of the last hour the device was running. |
| {device} cycles per hour | Off→on starts per hour over the last hour — surfaces short-cycling. |
| {TRV} valve position | The last commanded valve opening % (in `mpc` mode). |
| Running mean outdoor temperature | The slow exponential running mean of the outdoor temperature driving adaptive comfort. |
| Status (diagnostic) | `initializing` during the post-restart warm-up, then `ok`, or `degraded` once a managed device is unavailable or no temperature source can be found. Any offline devices are listed in its `unavailable_devices` attribute. |
| Home average source | Where the home averages come from: `computed` (managed areas' mean), `external` (your override sensors), `fallback` (override configured but unusable — computed mean standing in), or `mixed`; per-reading detail and the configured sensors in its attributes. |
| HVAC action reason | Plain-language headline of why the home is heating/cooling/idle/paused (e.g. `Heating`, `Frost protection`, `Paused — window open`), with a per-device breakdown in its attributes. |

## Binary sensors

| Binary sensor | Description |
|---------------|-------------|
| Window open | On when any managed area reports a window/door open (open areas listed in attributes). |
| Frost protection active | On when any device is in forced frost-protection heating. |
| Dehumidifying | On when an AC is running dry mode for the dew-point guard. |

Next: [Services & automations](../guides/services-automations.md)
