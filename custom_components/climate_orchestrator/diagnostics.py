"""Downloadable diagnostics for Climate Orchestrator.

Surfaces the full runtime picture — merged config, resolved settings, the latest
sensor snapshot, per-device decisions, learned MPC parameters, and the adaptive
state — so a problem can be understood from the downloaded JSON alone.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.core import HomeAssistant

from .coordinator import SmartClimateConfigEntry
from .settings import resolve_settings


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: SmartClimateConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    coordinator = entry.runtime_data
    settings = resolve_settings(hass, entry.entry_id)
    data = coordinator.data

    return {
        "config": {**entry.data, **entry.options},
        "settings": asdict(settings),
        "snapshot": {
            "home_avg_temperature": data.home_avg_temperature,
            "home_avg_humidity": data.home_avg_humidity,
            "status": data.status.value,
            "degraded": data.degraded,
            "available_devices": sorted(data.available_devices),
            "unavailable_devices": sorted(data.unavailable_devices),
            "stale_sensors": sorted(data.stale_sensors),
            "readings": {eid: asdict(r) for eid, r in data.readings.items()},
        },
        "decisions": {
            eid: asdict(decision)
            for eid, decision in coordinator.last_decisions.items()
        },
        "adaptive_comfort": {
            "running_mean_outdoor": coordinator.running_mean_outdoor,
            "shifted_cool_edge": coordinator.adaptive_band_high,
        },
        "temperature_slope": coordinator.temperature_slope,
        "hvac_action_reason": coordinator.hvac_action_reason(),
        "devices": {
            eid: {
                "action": coordinator.device_action(eid),
                "command": coordinator.device_command_attrs(eid),
                "valve_position": coordinator.valve_position(eid),
                "runtime_fraction": coordinator.device_runtime_fraction(eid),
                "cycles_per_hour": coordinator.device_cycles_per_hour(eid),
            }
            for eid in coordinator.device_ids
        },
        "mpc": coordinator.mpc_diagnostics(),
        "maintenance_last": coordinator._last_maintenance,
    }
