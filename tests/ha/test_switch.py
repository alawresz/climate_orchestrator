"""Tests for the feature-flag switches."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_switch_defaults(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Frost protection defaults on; AC heating assist defaults off."""
    cid = init_integration.entry_id
    assert (
        hass.states.get(entity_id_for("switch", f"{cid}_frost_protection")).state
        == "on"
    )
    assert (
        hass.states.get(entity_id_for("switch", f"{cid}_ac_heating_assist")).state
        == "off"
    )


async def test_toggle_switch(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Turning a switch off updates its state."""
    entity_id = entity_id_for("switch", f"{init_integration.entry_id}_frost_protection")
    await hass.services.async_call(
        "switch", "turn_off", {ATTR_ENTITY_ID: entity_id}, blocking=True
    )
    assert hass.states.get(entity_id).state == "off"
