# Services & automations

## Services

Two services for radiator-valve upkeep, callable from automations, scripts, or
Developer Tools → Actions (target the whole-home `climate` entity):

- **`climate_orchestrator.run_valve_maintenance`** — drive the TRV valves fully open then
  closed once, to stop a valve seizing or scaling when held at one position for a
  long time. Optional `trvs:` to scope to specific valves (default: all). The
  **Automatic valve maintenance** switch runs this on a schedule.
- **`climate_orchestrator.reset_mpc_learning`** — forget the learned MPC thermal model
  for some or all TRVs, so they re-learn from scratch. Optional `trvs:` to scope.

```yaml
# Exercise all TRV valves once
action: climate_orchestrator.run_valve_maintenance
target:
  entity_id: climate.climate_orchestrator
```

```yaml
# Re-learn one room's thermal model from scratch
action: climate_orchestrator.reset_mpc_learning
target:
  entity_id: climate.climate_orchestrator
data:
  trvs:
    - climate.bedroom_trv
```

## Events

Operational transitions are announced on the event bus as
`climate_orchestrator_event`, discriminated by a `type` field — one event per
*edge*, never one per cycle, so they're safe to notify on directly:

| `type` | When | Extra data |
|--------|------|------------|
| `frost_protection_started` / `_ended` | A room crosses the frost-protection temperature (either way). | `entities` — the devices in forced heating. |
| `dehumidifying_started` / `_ended` | The dew-point guard puts an AC in (or out of) dry mode. | `entities` |
| `window_pause_started` / `_ended` | An open window starts/stops suppressing one device (after the grace delay). | `entity_id`, `area_id` |
| `status_changed` | The status sensor moves between `ok` / `degraded` / `initializing`. | `from`, `to`, `unavailable_devices` |
| `device_ignoring_commands` / `device_commands_applied` | The [command-ignored watchdog](../reference/troubleshooting.md#repairs) trips / the device complies again. | `entity_id`, `commanded_mode` |
| `boost_started` / `boost_ended` | The boost preset engages / reverts. | started: `direction`, `previous_preset`, `until`; ended: `reason` (`expired`/`cancelled`), `reverted_to` |
| `manual_override_started` / `_ended` | A [manual takeover](how-it-controls.md#manual-override-takeover) of one device begins / ends. | `entity_id`; started: `duration_minutes`; ended: `reason` (`expired`/`reasserted`/`unavailable`/`frost_protection`) |

Trigger on them like any bus event:

```yaml
automation:
  - alias: "Frost protection engaged"
    triggers:
      - trigger: event
        event_type: climate_orchestrator_event
        event_data:
          type: frost_protection_started
    actions:
      - action: notify.mobile_app_your_phone
        data:
          title: "Frost protection!"
          message: "Forced heating: {{ trigger.event.data.entities | join(', ') }}"
```

## Bell notifications

The two conditions worth interrupting you for — **frost protection active**
and **status degraded** — also raise a notification in Home Assistant's
notification panel (the sidebar bell), and dismiss it again by themselves
when the condition clears. The **Event notifications** switch turns this off;
bus events keep firing regardless, so your own automations are unaffected.

## Automation recipes

Get notified when the orchestrator degrades (a device went offline or the
control loop keeps failing):

```yaml
automation:
  - alias: "Climate Orchestrator needs attention"
    triggers:
      - trigger: state
        entity_id: sensor.climate_orchestrator_status
        to: "degraded"
        for: "00:05:00"
    actions:
      - action: notify.mobile_app_your_phone
        data:
          title: "Climate Orchestrator degraded"
          message: >-
            {{ state_attr('sensor.climate_orchestrator_status',
                          'unavailable_devices') | join(', ') or 'See log' }}
```

Switch the whole home to the away preset when everyone leaves, and back on
return:

```yaml
automation:
  - alias: "Climate follows presence"
    triggers:
      - trigger: state
        entity_id: zone.home
    actions:
      - action: climate.set_preset_mode
        target:
          entity_id: climate.climate_orchestrator
        data:
          preset_mode: >-
            {{ 'away' if states('zone.home') | int == 0 else 'home' }}
```

!!! tip
    The [binary sensors](../reference/entities.md#binary-sensors) (Window open, Frost
    protection active, Dehumidifying) and the diagnostic sensors are built for
    exactly this kind of dashboard and automation use.

Next: [Troubleshooting](../reference/troubleshooting.md)
