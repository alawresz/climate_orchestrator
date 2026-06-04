# First setup

Climate Orchestrator is configured entirely from the UI — one short form, no
YAML. Only a single instance is allowed: one config entry drives one whole-home
entity. This page walks through every field in the setup dialog (the same form
appears later under **Configure** if you want to change anything).

## Before you start: areas and sensors

Sensors are matched automatically from each device's Home Assistant **area** —
you never pick a sensor per device. For that to work:

1. Assign each TRV and AC to the area (room) it actually serves.
2. On each of those areas, assign a temperature sensor (and ideally a humidity
   sensor) under **Settings → Areas → *Related sensors***.

A device whose area has no temperature sensor isn't broken — it just falls back
to being controlled against the whole-home average instead of its own room.

!!! tip
    The humidity sensor is optional but worth adding: with it, control runs off
    a humidity-adjusted "feels-like" temperature instead of the bare number (see
    [How it controls](../guides/how-it-controls.md)).

## The setup form

Open **Settings → Devices & Services → Add Integration → "Climate
Orchestrator"**. The form has these fields:

### Devices (pick at least one)

| Field | What it is |
|-------|------------|
| **Radiator valves (TRVs)** | The radiator-valve `climate` entities to orchestrate. |
| **Air conditioners** | The air-conditioner `climate` entities to orchestrate. |

You must select at least one TRV or AC — the form rejects an empty selection
("Select at least one radiator valve or air conditioner."). The thermostat
adapts to what you pick: TRVs only gives a heat-only thermostat, an AC only
gives cool-only, and both together give the full heat/cool band.

### Optional sources

| Field | What it is |
|-------|------------|
| **Outdoor temperature sensor (optional)** | A `sensor` with the temperature device class. Used for outdoor gating and adaptive cooling comfort. |
| **Weather entity (optional, for forecast preconditioning)** | A `weather` entity that provides the hourly forecast for preconditioning. |
| **Whole-home average temperature sensor (optional, overrides the computed average)** | Replaces the computed whole-home average temperature; falls back to computed if unavailable. |
| **Whole-home average humidity sensor (optional, overrides the computed average)** | Replaces the computed whole-home average humidity; falls back to computed if unavailable. |

The override sensors replace the computed whole-home average wherever it's
used; how that average drives control — and what happens when an override goes
stale — is covered in [How it controls](../guides/how-it-controls.md).

### Presets

| Field | Default | What it is |
|-------|---------|------------|
| **Presets** | Home, Away, Sleep | Which presets the thermostat offers. Only selected presets get editable setpoint `number` entities; the manual band is always available. |

### Advanced: TRV discovery hints

| Field | Default | What it is |
|-------|---------|------------|
| **TRV valve-opening number name hints (comma-separated)** | `valve_opening_degree, valve_opening, valve_position` | Name fragments used to discover each TRV's valve-opening `number` entity (MPC mode). |
| **TRV local-calibration number name hints (comma-separated)** | `local_temperature_calibration, temperature_calibration, temperature_offset` | Name fragments used to discover each TRV's local-calibration `number` entity (offset mode). |

These only matter for the `mpc` and `offset` [calibration modes](../guides/hardware.md).
The defaults match Zigbee2MQTT naming; if you add a TRV from another brand
whose entities are named differently, add its naming here (comma-separated) so
MPC/offset can find them.

!!! note
    Everything else — presets, toggles, tuning numbers — lives as runtime
    entities on the hub device, not in this dialog. You adjust them live, no
    reload needed.

## What appears after setup

A single hub device is created exposing the whole-home
`climate.climate_orchestrator` entity, the home-average / feels-like / slope /
adaptive sensors, per-device diagnostic sensors, the window/frost/dehumidifying
binary sensors, the **TRV calibration mode** select, the feature-toggle
switches, and the tuning numbers (including per-preset band edges and a
per-area band offset). The full list with descriptions is in the
[reference](../reference/entities.md).

## Where to go next

- [How it controls](../guides/how-it-controls.md) — understand the band, the asymmetric
  trigger, and the per-cycle logic.
- [Comfort features](../guides/comfort-features.md) — presets, per-area offsets, adaptive
  cooling, forecast preconditioning.
- [Reference](../reference/entities.md) — every entity and setting, with defaults.

Next: [How it controls](../guides/how-it-controls.md)
