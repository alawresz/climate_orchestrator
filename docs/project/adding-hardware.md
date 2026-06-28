# Adding hardware support

Climate Orchestrator drives any standard Home Assistant `climate` entity out of
the box. When a specific device needs different handling — a non-standard
attribute, a capability it misreports, or differently-named valve/calibration
numbers — that lives in a **device profile**, not in the adapter or coordinator.
This page shows how to add one. See
[ADR-0001](../decisions/0001-device-profiles.md) for why the seam exists.

## The model

A [`DeviceProfile`][src] is a small, frozen value object describing how to talk
to one class of device. Every field defaults to the standard climate contract,
so a bare `DeviceProfile()` *is* the generic behaviour; a concrete profile sets
only what differs:

| Field               | Purpose                                           | Default                 |
| ------------------- | ------------------------------------------------- | ----------------------- |
| `name`              | Identifier for logs/tests                         | `"generic"`             |
| `current_temp_attr` | Attribute carrying the room temperature           | `current_temperature`   |
| `target_temp_attr`  | Attribute carrying the active setpoint            | `temperature`           |
| `valve_hints`       | Name fragments for the valve-opening `number`     | `None` (use configured) |
| `calibration_hints` | Name fragments for the local-calibration `number` | `None` (use configured) |

Profiles are matched per entity by `(integration, manufacturer, model)`, read
from the device registry. The first matcher that returns `True` wins; otherwise
the device gets `GENERIC`. The matching and parsing are pure, so a profile is
unit-testable without a running Home Assistant.

## Adding a profile

Everything happens in `custom_components/climate_orchestrator/devices/profiles.py`.

1. **Describe the device.** Add a `DeviceProfile`, overriding only the quirky
   fields:

    ```python
    ACME_TRV = DeviceProfile(
        name="acme_trv",
        # This valve reports the room under a vendor attribute...
        current_temp_attr="local_temperature",
        # ...and names its valve number differently.
        valve_hints=("acme_valve_level",),
    )
    ```

2. **Match it.** Add a predicate over the lower-cased identity and register it
   in `_PROFILES` (tried in order, first match wins):

    ```python
    def _is_acme_trv(integration, manufacturer, model):
        return manufacturer == "acme" and model is not None and "trv" in model

    _PROFILES = (
        (_is_sonoff_trvzb, SONOFF_TRVZB),
        (_is_acme_trv, ACME_TRV),
    )
    ```

    Match on whatever is stable for the device. Model strings often carry across
    Zigbee2MQTT and ZHA where the manufacturer string does not — the SONOFF
    TRVZB matcher keys off the model alone for exactly this reason.

3. **Test it.** Add a pure case to `tests/unit/devices/test_profiles.py`
   (resolution + any custom parsing) and, if it has a real device shape, an
   entity-resolution case to `tests/ha/test_device_profiles.py`.

That's the whole change — no edits to `ClimateAdapter` or the coordinator.

## What is *not* a profile (yet)

Profiles currently cover **reading** and **discovery**. Devices with **write**
quirks — a setpoint that must be sent before the mode, a settle delay, a mode
toggle to commit a calibration — are the deferred Phase 4 in
[ADR-0001](../decisions/0001-device-profiles.md): a pure write-strategy hook
on `DeviceProfile`, to be added the day a real device needs it rather than
speculatively. If you have such a device, that's the place to extend.

[src]: https://github.com/alawresz/climate_orchestrator/blob/main/custom_components/climate_orchestrator/devices/profiles.py
