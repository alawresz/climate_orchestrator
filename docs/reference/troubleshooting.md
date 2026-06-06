# Troubleshooting

## The Status sensor

The whole-home **Status** diagnostic sensor is the first place to look:

- **`initializing`** — the post-restart warm-up. Sensors and devices are still
  coming back; some repairs are deliberately held back during this window.
- **`ok`** — everything has a reading and every managed device is reachable.
- **`degraded`** — a managed device is unavailable or no temperature source can
  be found. Any offline devices are listed in the sensor's
  `unavailable_devices` attribute.

!!! tip
    See [Services & automations](../guides/services-automations.md) for a ready-made
    automation that notifies you when the status turns `degraded`.

## Repairs

A notice is raised (and auto-cleared) for silent misconfigurations:

- a TRV in `mpc`/`offset` mode whose `valve_opening_degree` /
  `local_temperature_calibration` number can't be found (falls back to `target`);
- **Adaptive cooling comfort** enabled with no outdoor sensor;
- **Forecast preconditioning** enabled with no weather entity;
- **Forecast preconditioning** enabled with a weather entity whose hourly
  forecast has been unavailable for hours (the fetch keeps failing or returns
  nothing) — the feature is silently inert until it recovers;
- **AC heating assist** enabled while no available air conditioner can heat —
  either none is selected, or the selected unit offers no `heat` mode, so the
  assist demand is computed and then discarded;
- **Dew point guard** enabled with an air conditioner configured but none that
  offers a `dry` mode (a radiator-only home never sees this — there's nothing
  to dehumidify through);
- **AC ignores open windows** enabled with no air conditioner configured, so the
  exemption has nothing to apply to;
- an area sensor that has gone stale (stopped reporting past the staleness
  timeout);
- an inverted comfort band (cool setpoint below the heat setpoint, leaving no
  neutral zone);
- a TRV in `mpc` mode whose thermal model has fit its room poorly for over a
  day — usually a weather-compensated radiator (district heating, outdoor-reset
  boiler) whose output the model's constant `gain` can't track; the notice
  suggests `offset` mode and clears once the model fits again;
- no usable temperature source for any managed device.

The capability checks above only consider *available* air conditioners — an AC
that's merely offline has unknown modes, so it isn't mistaken for one that
can't heat or dry.

The last two (stale sensor, no temperature source) are transient right after a
Home Assistant restart, so while the **Status** sensor reads `initializing`
they're held back — they only surface once the warm-up window has elapsed and
the gap is therefore real.

A separate notice appears if the control cycle itself fails several times in
a row — devices stop receiving fresh commands while readings continue — and
clears on the next successful cycle.

A per-device **command-ignored** notice catches the opposite failure mode: the
service calls *succeed*, but the device's state never reflects the commanded
HVAC mode for five minutes straight — it's silently ignoring them, so its room
isn't actually being controlled. Typical culprits: a child/temperature lock
engaged on the device, a weak Zigbee/radio link, a dying battery, or its
integration no longer talking to the hardware. The notice clears as soon as
the device applies a command (and isn't raised for *loudly* failing devices —
those are covered above — or unavailable ones, which the **Status** sensor
reports).

Learned state (MPC models, the adaptive bias, the running-mean outdoor
temperature, and the per-device demand latch) is persisted, so a restart resumes
where it left off.

## Download diagnostics

**Download Diagnostics** from the device page (⋮ → *Download diagnostics*) for a
full JSON dump: merged config, resolved settings, the latest sensor snapshot,
per-device decisions and reasons, learned MPC parameters, and the adaptive
state.

## Enable debug logging

For a per-cycle trace of what the orchestrator is doing (and why) — sensor
snapshots, per-device decisions, command writes, MPC learning, forecast
fetches — turn on debug logging for the integration. Either at runtime via
**Settings → Devices & Services → Climate Orchestrator → ⋮ → Enable debug
logging** (downloads the captured log when disabled again), or persistently in
`configuration.yaml`:

```yaml
logger:
  logs:
    custom_components.climate_orchestrator: debug
```

When reporting an issue, a debug log covering a few control cycles plus the
diagnostics JSON (above) is usually everything needed to reproduce it.

## FAQ

**My TRV's valve number isn't found (a repair says the calibration number is
missing).**
MPC and offset modes discover a TRV's `number` entities by name hints, which
default to Zigbee2MQTT naming (`valve_opening_degree` /
`local_temperature_calibration`). If your TRV brand names them differently, add
its naming (comma-separated) to the **TRV valve-opening** / **local-calibration
number name hints** fields in the integration's Configure dialog. Until then,
the device safely falls back to `target` mode. See
[First setup](../getting-started/first-setup.md).

**A room is being controlled against the home average instead of its own
sensor.**
The device's HA area has no temperature sensor assigned (or it has gone stale).
Assign one under **Settings → Areas → *Related sensors***, or check the stale
sensor's battery/connection. You can also raise the **Sensor staleness timeout**
number if your sensors legitimately report slowly.

**Adaptive cooling comfort / outdoor gating does nothing.**
Both need an outdoor temperature sensor configured in the integration options —
a repair notice points this out when one of the features is on without it.

**Forecast preconditioning does nothing.**
It needs the **MPC calibration mode** *and* a weather entity that provides an
hourly forecast. Without the weather entity a repair notice asks you to add one
(or turn the feature off).

**The thermostat shows a different temperature than my sensor.**
While **Comfort index targeting** is on, the climate entity's current
temperature is the humidity-adjusted feels-like value; the raw dry-bulb reading
is kept in the `dry_bulb_temperature` attribute.

**MPC mode isn't doing anything yet.**
Expected right after install or a learning reset — it needs a few hours of
heating to fit a room's model (see [known limitations](limitations.md)). Watch
the *MPC learning status* sensors move from `learning` to `ready`.

Next: [Known limitations](limitations.md)
