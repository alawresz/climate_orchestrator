"""Tests for resolving runtime settings from the tuning entities."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_orchestrator.const import RELEASE_OFFSET_DEFAULT
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from custom_components.climate_orchestrator.settings import (
    NUMBER_SETTINGS,
    resolve_settings,
)


async def test_resolve_returns_defaults(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """With nothing changed, the resolver returns the defaults."""
    settings = resolve_settings(hass, init_integration.entry_id)
    assert settings.release_offset == RELEASE_OFFSET_DEFAULT
    assert settings.frost_protection is True
    assert settings.ac_heating_assist is False


async def test_current_settings_resolves_before_the_first_cycle(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """A fresh coordinator resolves settings on demand (no cycle cache yet).

    Entities can read ``current_settings()`` before the first control cycle
    has populated the per-cycle cache; it must fall back to a live resolve.
    """
    config_entry.add_to_hass(hass)
    coordinator = SmartClimateCoordinator(hass, config_entry)
    settings = coordinator.current_settings()
    assert settings.release_offset == RELEASE_OFFSET_DEFAULT


async def test_resolve_reflects_entity_changes(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Changing a number/switch is reflected in resolved settings."""
    cid = init_integration.entry_id
    await hass.services.async_call(
        "number",
        "set_value",
        {
            ATTR_ENTITY_ID: entity_id_for("number", f"{cid}_ac_setpoint_bias"),
            "value": 2.5,
        },
        blocking=True,
    )
    await hass.services.async_call(
        "switch",
        "turn_off",
        {ATTR_ENTITY_ID: entity_id_for("switch", f"{cid}_comfort_index_targeting")},
        blocking=True,
    )

    settings = resolve_settings(hass, cid)
    assert settings.ac_setpoint_bias == 2.5
    assert settings.comfort_index_targeting is False


async def test_out_of_range_entity_states_are_clamped(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Developer Tools can set a number past its bounds; the resolver clamps.

    The number platform enforces min/max on service calls, but a raw state
    write (or a state restored from a release with wider limits) bypasses it.
    """
    cid = init_integration.entry_id
    by_key = {s.key: s for s in NUMBER_SETTINGS}
    # Bypass the number platform, as Developer Tools' state writer would.
    hass.states.async_set(entity_id_for("number", f"{cid}_window_open_delay"), "-10")
    hass.states.async_set(entity_id_for("number", f"{cid}_ac_setpoint_bias"), "999")

    settings = resolve_settings(hass, cid)
    assert settings.window_open_delay == by_key["window_open_delay"].min_value
    assert settings.ac_setpoint_bias == by_key["ac_setpoint_bias"].max_value
