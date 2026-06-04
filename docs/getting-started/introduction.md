# Introduction

Climate Orchestrator turns a pile of independent TRVs and air conditioners
into one coordinated whole-home climate system: each device works toward the
same comfort band, from the sensor in its own room. This page is the feature
tour; if you just want it running, jump to [Installation](installation.md).

## What it does

- **One control surface.** A single `climate.climate_orchestrator` entity with two
  setpoints (a heating edge and a cooling edge) controls all your TRVs and ACs.
- **Configurable presets, plus boost.** Pick which presets (home/away/sleep/
  boost) the thermostat offers — only those create tuning entities. **Boost**
  temporarily pushes the band in the right direction (heat or cool) and
  auto-reverts after a set duration.
- **Manual changes are respected.** Adjust a TRV or the AC directly (on the
  device or its own entity) and the orchestrator stands back from *that* device
  for a configurable window instead of silently fighting you.
- **Area-matched sensors.** Each device reads the temperature/humidity sensor on
  its Home Assistant **area** (Settings → Areas → *Related sensors*); a home-wide
  average is computed across all of them.
- **Asymmetric trigger.** A device engages when *its area OR the home average*
  crosses an edge, and disengages only when *both* are back at target.
- **Comfort index.** Control runs off a humidity-adjusted "feels-like" (apparent)
  temperature, with a dew-point guard that can run the AC's dry mode.
- **Per-area offset.** A per-area number can run one room warmer or cooler than
  the rest, biasing only that area without changing the whole-home band.
- **Coordinated heat/cool.** A neutral band between the two setpoints keeps
  heating and cooling from fighting; frost protection, window-open (with a grace
  delay), and outdoor-temp gating are layered guards.
- **AC drive.** ACs are commanded a setpoint biased below the real target so the
  AC's own sensor doesn't satisfy before the room does — and that bias
  **self-tunes** with integral feedback so it lands the room on target over time.
  Fan/swing controls are surfaced and forwarded when the AC supports them.
- **Adaptive cooling comfort (opt-in).** When it's genuinely hot outside, the
  cooling setpoint is allowed to drift gently upward (the heat edge never moves),
  saving energy on extreme days without chasing a setpoint you wouldn't pick
  anyway. Needs an outdoor sensor.
- **MPC calibration (opt-in).** TRVs can be driven by a learning MPC valve
  controller or a local-temperature offset; learned thermal parameters persist
  across restarts. With a weather entity, **forecast preconditioning** feeds the
  hourly forecast into the optimiser so a radiator pre-heats a room ahead of a
  cold spell.
- **Observability.** Per-device diagnostics (action, runtime, cycles, valve %,
  learned MPC model), a whole-home **status** sensor (`initializing`/`ok`/
  `degraded`), Repairs notices that flag silent misconfigurations (including a
  watchdog for devices that accept commands but ignore them), **bus events** for
  every notable transition, and self-clearing bell notifications for the
  important ones.
- **Resilient.** One device or sensor going offline never takes the whole-home
  entity down, and a frozen ("stale") sensor is detected and dropped rather than
  trusted.

## Requirements

- Home Assistant `2024.12` or newer.
- `scipy` (declared in the manifest; Home Assistant installs it automatically on
  first setup).
- Each managed device's **HA area** should have a temperature (and ideally
  humidity) sensor assigned under *Related sensors*; otherwise that device falls
  back to the home-wide average.

## Project status

The integration is feature-complete against the design and heavily unit- and
integration-tested. The hardware-specific TRV valve/offset writes are **not yet
validated on real devices**, so the default `target`
[calibration mode](../guides/hardware.md) is the safe baseline.

!!! warning
    As with any early-stage thermostat replacement, keep an independent fallback
    for heating/cooling until it has proven itself in your setup.

Next: [Installation](installation.md)
