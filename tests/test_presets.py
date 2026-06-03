"""Tests for the editable per-preset band entities."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.climate import (
    ATTR_PRESET_MODE,
    SERVICE_SET_PRESET_MODE,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_orchestrator.const import DEFAULT_PRESETS


async def _set_number(hass: HomeAssistant, entity_id: str, value: float) -> None:
    await hass.services.async_call(
        "number",
        "set_value",
        {ATTR_ENTITY_ID: entity_id, "value": value},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_preset_numbers_exist_with_defaults(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Each preset exposes editable heat/cool edge numbers at their defaults."""
    cid = init_integration.entry_id
    heat = entity_id_for("number", f"{cid}_preset_home_heat")
    cool = entity_id_for("number", f"{cid}_preset_home_cool")
    assert float(hass.states.get(heat).state) == DEFAULT_PRESETS["home"][0]
    assert float(hass.states.get(cool).state) == DEFAULT_PRESETS["home"][1]


async def test_editing_active_preset_updates_band(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Editing the active preset's edge moves the climate setpoint live."""
    cid = init_integration.entry_id  # default preset is "home"
    climate = entity_id_for("climate", cid)
    await _set_number(hass, entity_id_for("number", f"{cid}_preset_home_heat"), 19.0)
    assert hass.states.get(climate).attributes["target_temp_low"] == 19.0


async def test_selecting_preset_uses_edited_numbers(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Selecting a preset applies its (edited) edge values."""
    cid = init_integration.entry_id
    climate = entity_id_for("climate", cid)
    await _set_number(hass, entity_id_for("number", f"{cid}_preset_sleep_cool"), 22.0)

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: climate, ATTR_PRESET_MODE: "sleep"},
        blocking=True,
    )
    assert hass.states.get(climate).attributes["target_temp_high"] == 22.0
