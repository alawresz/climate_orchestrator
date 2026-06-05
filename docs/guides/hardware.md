# Hardware

The control loop decides *whether* each device should heat or cool. This page
covers *how* that intent becomes commands, which differs for radiator valves and
air conditioners — plus the valve-maintenance tooling that keeps TRVs healthy.

## Driving the radiators (TRV calibration modes)

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
       **learning** to **ready**; the fitted values show as attributes on the
       **MPC learning status** diagnostic and persist across restarts.
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
`mpc`/`offset` can't act and the device falls back to `target` safely.

!!! warning
    The hardware-specific TRV valve/offset writes are not yet validated on real
    devices. Validate on your hardware before trusting it on the radiators —
    `target` is the safe baseline.

For the full maths behind MPC, see the [MPC deep dive](../internals/mpc.md).

## Driving the air conditioner

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

## Valve maintenance

A TRV valve held at one position for a long time can seize or scale. Two ways to
exercise it:

- **Manual service.** Call `climate_orchestrator.run_valve_maintenance` to drive
  the TRV valves fully open then closed once. Optional `trvs:` scopes it to
  specific valves (default: all). See
  [Services & automations](services-automations.md).
- **Automatic.** Turn on the **Automatic valve maintenance** switch to run the
  same exercise periodically, every **Valve maintenance interval** days
  (default 30). It's skipped while a room is actively heating. If no valve
  opening numbers can be found (hint mismatch, renamed devices), a warning is
  logged and the run is deferred to the next interval.

Next: [Reference](../reference/entities.md)
