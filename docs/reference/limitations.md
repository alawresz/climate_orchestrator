# Known limitations

- **One home per Home Assistant instance** — a single config entry drives one
  whole-home entity. Per-room *bias* exists (area band offsets), but rooms
  don't have independent schedules; use presets + automations for time-based
  behaviour.
- **Rooms need their own sensors for full local control.** A device whose HA
  area has no temperature sensor is controlled against the home average only.
- **Valve/calibration discovery is name-based.** MPC and offset modes find a
  TRV's `number` entities by name hints (Zigbee2MQTT/SONOFF defaults,
  configurable in options); a brand with different naming needs its hints set.
- **MPC learns from history.** After install or a learning reset, valve
  control starts from conservative priors and typically needs a few hours of
  heating to fit a room's model (watch the *MPC learning status* sensors).
- **MPC assumes a constant radiator output.** The learned model treats heating
  power at a given valve opening as fixed (it learns one `gain`). On a
  **weather-compensated hydronic system** — most district heating, and condensing
  boilers with an outdoor-reset curve — the supply-water temperature rises as it
  gets colder, so the *same* valve opening emits more heat in harsh weather. MPC
  captures the increased heat *loss* (the `loss·(room − outdoor)` term) but not
  the increased *output*; it re-learns `gain` over a rolling window, so comfort
  is held by feedback, but expect a worse model fit and weaker preconditioning,
  with transient over/undershoot when the supply temperature shifts quickly. On
  such systems **`offset` calibration mode is sometimes the better choice** — it lets
  the valve's own loop modulate against whatever water temperature is present. A
  repair notice flags a TRV whose MPC model fits persistently poorly.
- **Forecast preconditioning needs an hourly forecast** from the configured
  weather entity, and only ever *raises* heating — it won't pre-cool.
- **Manual-override detection is heuristic.** A takeover is recognised by its
  trajectory (the device *was* at the commanded state, then moved away), so
  two rare races exist: a manual change made while a command is still in
  flight is read as non-compliance instead (the watchdog's case, no
  takeover), and a state report landing in the same instant the command
  itself changes can start a spurious takeover. Both windows are
  milliseconds wide and the consequences bounded — at worst one device is
  left alone for the **Manual override duration**, any interaction with the
  thermostat reasserts control, and frost protection punches through
  regardless.
- **Devices must be standard HA `climate` entities** exposing the usual
  attributes (`hvac_modes`, `current_temperature`, min/max). Anything that
  does is fair game; anything that doesn't isn't.

Next: back to the [introduction](../getting-started/introduction.md), or dive into the
[internals](../internals/architecture.md).
