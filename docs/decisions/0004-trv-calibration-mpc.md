# ADR-0004: TRV calibration strategies, and model-predictive valve control

**Status:** Accepted
**Date:** 2026-06 (retrospective)

## Context

A radiator valve's built-in temperature sensor sits on the hot radiator, so it
reads warmer than the room and closes the valve before the room is actually
warm. Three things are true at once: (1) users have wildly different TRV
hardware and trust levels, (2) some valves expose a `local_temperature_calibration`
number, some expose a raw `valve_opening_degree`, some expose neither, and (3)
a radiator + room is a slow, lagged thermal system where naive bang-bang control
overshoots and oscillates.w

We need a way to drive valves well *without* assuming any one capability is
present, and without forcing every user onto a complex control mode.

## Decision

Offer **three calibration modes**, selectable per install (the
`TRV calibration mode` select), in increasing order of capability and ambition:

- **`target` (default, safe).** Command the valve to the band's heat target and
  trust its own loop. Works on any climate entity; inherits the TRV's sensor
  bias. The recommended starting point.
- **`offset`.** Write `local_temperature_calibration = room − TRV's own reading`
  so the valve's internal loop regulates to the *room* temperature. Needs a
  calibration number.
- **`mpc`.** Drive the `valve_opening_degree` directly with **model-predictive
  control**: a first-order per-room thermal model (`dT/dt = gain·valve − loss·(room − outdoor)`) whose `gain`/`loss` are learned online by
  least-squares system identification (SciPy), a Kalman filter to smooth the
  slow/noisy sensor between updates, and a short look-ahead optimiser (which
  also consumes the weather forecast for preconditioning).

Default to the mode that always works; let users opt up.

For *why MPC rather than a PID*: the plant is slow and lagged with a large
measurable disturbance (outdoor temperature). A learned first-order model with
look-ahead handles the lag and feed-forwards the disturbance directly; a PID
would need careful per-room retuning and still lacks feed-forward. The model is
also introspectable — `gain`/`loss` surface as diagnostics — where PID gains are
opaque.

## Options Considered

| Option                    | Pros                                                             | Cons                                                   |
| ------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------ |
| Single `target` mode only | Trivial; universal                                               | Inherits TRV sensor bias; no path to better control    |
| `target` + `offset` only  | Fixes the bias cheaply                                           | Still bang-bang; needs a calibration number            |
| Add `mpc` (chosen)        | Handles lag + outdoor feed-forward; introspectable; best comfort | SciPy dependency; learning code to maintain and harden |
| PID instead of MPC        | Familiar                                                         | Per-room tuning; no feed-forward; opaque gains         |

## Consequences

- **Easier:** users get a safe default and a clear upgrade path; MPC's learned
  parameters are observable and persisted across restarts.
- **Harder:** the MPC path carries real numerical risk (system identification,
  matrix conditioning) — mitigated by the pure-core test discipline
  ([ADR-0002](0002-pure-control-core.md)), Hypothesis properties, and explicit
  numerical hardening; SciPy runs in an executor to keep the event loop free.
- **Discovery** of the per-mode `number` entities is by name hint, now folded
  into device profiles ([ADR-0001](0001-device-profiles.md)).
- **Known limitation / to revisit:** the model learns a single `gain`, so it
  assumes a constant radiator output and is mis-specified for
  weather-compensated hydronic systems (district heating, outdoor-reset
  boilers), where the same valve opening emits more heat in colder weather.
  Comfort still holds (closed-loop, rolling re-fit), but the fit degrades; a
  [poor-fit repair](../reference/troubleshooting.md#repairs) flags it and
  `offset` mode is the recommended fallback. The proper fix is an optional
  supply-temperature input changing the heat term to `k·valve·(supply − room)`,
  deferred until there's demand and a sensor to drive it.
