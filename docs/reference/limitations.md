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
- **Forecast preconditioning needs an hourly forecast** from the configured
  weather entity, and only ever *raises* heating — it won't pre-cool.
- **Devices must be standard HA `climate` entities** exposing the usual
  attributes (`hvac_modes`, `current_temperature`, min/max). Anything that
  does is fair game; anything that doesn't isn't.

Next: back to the [introduction](../getting-started/introduction.md), or dive into the
[internals](../internals/architecture.md).
