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
