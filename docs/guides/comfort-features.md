# Comfort features

Beyond the core control loop, a handful of features shape *where* the band sits:
presets, a manual band, per-area offsets, and two opt-in features that adapt the
band to the weather.

## Presets and their edges

Each preset (Home / Away / Sleep) is a pair of setpoints — a heat edge and a
cool edge. Selecting a preset on the thermostat applies its two edges; editing
the active preset's number moves the live setpoint at once. Heating runs below
the heat setpoint, cooling above the cool setpoint, nothing between. Each edge
is editable within 7–35 °C.

| Preset | Heat setpoint | Cool setpoint |
|--------|:-------------:|:-------------:|
| Away | 16.0 °C | 30.0 °C |
| Home (default) | 20.5 °C | 24.5 °C |
| Sleep | 19.5 °C | 23.5 °C |

The preset edges live as `number` entities on the hub device (e.g. *Preset Home
heat setpoint*), so automations can edit them too.

Don't need all three? The **Presets** multi-select in the integration's
Configure dialog narrows the offering: deselected presets disappear from the
thermostat and their setpoint numbers aren't created (existing ones are cleaned
up). The manual band is always available. If the *active* preset is
deselected, the thermostat falls back to Home — or to manual when Home isn't
selected either.

## The manual band

You don't have to go through a preset: moving the setpoints directly on the
`climate.climate_orchestrator` entity adjusts the live band. With both TRVs and
an AC configured you get two setpoints (the band); with only one device kind, a
single setpoint (heat-only or cool-only) — see
[How it controls](how-it-controls.md).

## Per-area band offsets

One band still doesn't suit every room equally, so each managed area gets a
**`<area>` band offset** number (default 0 °C, range −5 to 5):

- a **positive** value shifts that area's whole band up — the room heats sooner
  and stops cooling later, so it runs **warmer**;
- a **negative** value runs it cooler.

The offset biases only that area's own reading, never the home average, so
nudging the bathroom warmer doesn't drag the rest of the house with it.

## Relaxing the cooling when it's hot out (Adaptive cooling comfort)

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

The adjusted cool edge is *always computed* (the **Adaptive cool setpoint**
sensor previews it even when the toggle is off) but only *applied* when the toggle
is on, which requires an outdoor sensor.

!!! tip
    Watch the **Adaptive cool setpoint** sensor through a hot week before
    enabling the toggle — it shows exactly what the feature would do, with no
    effect on control.

## Pre-heating from the forecast (Forecast preconditioning)

With **Forecast preconditioning** on (optional, off by default, **MPC calibration
mode** only), a radiator can start warming a room *before* a cold spell arrives
instead of only reacting once the room has already cooled. The MPC valve
optimiser normally plans against the current outdoor temperature held flat; with
this on, it instead plans against the configured **weather entity's** hourly
forecast, interpolated onto the control step over the **Preconditioning
look-ahead** — a tunable number (0.5–8 h, default 2 h). If the forecast shows it getting colder, the optimiser opens the
valve more now to stay ahead of the loss.

To keep comfort safe it only ever *raises* the valve: the commanded opening is the
larger of the normal (react-to-now) result and the forecast-aware result, so the
forecast can pre-heat but never under-heat the present. The forecast is refreshed
about every 15 minutes. Needs a weather entity that provides an hourly forecast;
without one, a repair notice points you to add it (or turn the feature off).

See [Hardware](hardware.md) for what MPC calibration mode actually does, and the
[MPC deep dive](../internals/mpc.md) for the maths.

Next: [Hardware](hardware.md)
