"""Tests for the tuning number entities."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_UNIT_OF_MEASUREMENT,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_orchestrator.const import RELEASE_OFFSET_DEFAULT


async def test_number_uses_default(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A tuning number starts at its configured default."""
    entity_id = entity_id_for("number", f"{init_integration.entry_id}_release_offset")
    assert float(hass.states.get(entity_id).state) == RELEASE_OFFSET_DEFAULT


async def test_set_number_value(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Setting a tuning number updates its state."""
    entity_id = entity_id_for("number", f"{init_integration.entry_id}_release_offset")
    await hass.services.async_call(
        "number",
        "set_value",
        {ATTR_ENTITY_ID: entity_id, "value": 1.0},
        blocking=True,
    )
    assert float(hass.states.get(entity_id).state) == 1.0


async def test_number_units(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """The window-open delay reads in minutes; temperatures stay in °C."""
    cid = init_integration.entry_id
    delay = hass.states.get(entity_id_for("number", f"{cid}_window_open_delay"))
    frost = hass.states.get(entity_id_for("number", f"{cid}_frost_protection_temp"))
    assert delay.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfTime.MINUTES
    assert frost.attributes[ATTR_UNIT_OF_MEASUREMENT] == UnitOfTemperature.CELSIUS
