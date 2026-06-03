"""Tests for the diagnostics platform."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_orchestrator.diagnostics import (
    async_get_config_entry_diagnostics,
)
from tests.conftest import TRV_ENTITY


async def test_diagnostics_has_expected_sections(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The diagnostics dump exposes config, settings, snapshot and decisions."""
    diag = await async_get_config_entry_diagnostics(hass, init_integration)

    assert set(diag) >= {
        "config",
        "settings",
        "snapshot",
        "decisions",
        "adaptive_comfort",
        "mpc",
        "hvac_action_reason",
    }
    # Resolved settings are a flat dict of the tuning values.
    assert diag["settings"]["frost_protection"] is True
    # Snapshot carries per-device readings for the managed devices.
    assert TRV_ENTITY in diag["snapshot"]["readings"]
    # Each device has a recorded decision with a reason.
    assert "reason" in diag["decisions"][TRV_ENTITY]
