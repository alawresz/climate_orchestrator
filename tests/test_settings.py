"""Tests for resolving runtime settings from the tuning entities."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_orchestrator.const import RELEASE_OFFSET_DEFAULT
from custom_components.climate_orchestrator.settings import resolve_settings


async def test_resolve_returns_defaults(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """With nothing changed, the resolver returns the defaults."""
    settings = resolve_settings(hass, init_integration.entry_id)
    assert settings.release_offset == RELEASE_OFFSET_DEFAULT
    assert settings.frost_protection is True
    assert settings.ac_heating_assist is False


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
