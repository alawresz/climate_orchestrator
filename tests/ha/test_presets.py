"""Tests for the editable per-preset band entities and the preset selection."""

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
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
)

from custom_components.climate_orchestrator.const import (
    CONF_PRESETS,
    DEFAULT_PRESETS,
    DOMAIN,
    SELECTABLE_PRESETS,
)
from custom_components.climate_orchestrator.settings import enabled_presets
from tests.conftest import TRV_ENTITY


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


async def _setup_with_presets(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    presets: list[str],
) -> None:
    """Set up the integration with one TRV and an explicit preset selection."""
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat")
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_PRESETS: presets}
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def test_preset_selection_limits_modes_and_numbers(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Only selected presets appear on the climate entity and get numbers."""
    await _setup_with_presets(
        hass, config_entry, living_area, register_entity_in_area, ["home", "sleep"]
    )
    cid = config_entry.entry_id

    climate = hass.states.get(entity_id_for("climate", cid))
    assert climate.attributes["preset_modes"] == ["home", "sleep", "manual"]

    assert hass.states.get(entity_id_for("number", f"{cid}_preset_home_heat"))
    assert hass.states.get(entity_id_for("number", f"{cid}_preset_sleep_cool"))
    registry = er.async_get(hass)
    for edge in ("heat", "cool"):
        assert (
            registry.async_get_entity_id("number", DOMAIN, f"{cid}_preset_away_{edge}")
            is None
        )


async def test_deselecting_active_preset_falls_back(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A restored preset that is no longer selected falls back to home."""
    mock_restore_cache(
        hass,
        [State("climate.climate_orchestrator", "heat", {"preset_mode": "away"})],
    )
    await _setup_with_presets(
        hass, config_entry, living_area, register_entity_in_area, ["home", "sleep"]
    )
    climate = hass.states.get(entity_id_for("climate", config_entry.entry_id))
    assert climate.attributes[ATTR_PRESET_MODE] == "home"


async def test_deselecting_home_falls_back_to_manual(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Without home in the selection the default preset is manual."""
    await _setup_with_presets(
        hass, config_entry, living_area, register_entity_in_area, ["sleep"]
    )
    climate = hass.states.get(entity_id_for("climate", config_entry.entry_id))
    assert climate.attributes["preset_modes"] == ["sleep", "manual"]
    assert climate.attributes[ATTR_PRESET_MODE] == "manual"


async def test_deselected_preset_numbers_are_pruned(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> None:
    """Registry entries of a deselected preset's numbers are removed at setup."""
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat")
    config_entry.add_to_hass(hass)
    registry = er.async_get(hass)
    cid = config_entry.entry_id
    stale = [
        registry.async_get_or_create(
            "number", DOMAIN, f"{cid}_preset_away_{edge}", config_entry=config_entry
        ).entity_id
        for edge in ("heat", "cool")
    ]
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_PRESETS: ["home", "sleep"]}
    )

    assert await hass.config_entries.async_setup(cid)
    await hass.async_block_till_done()

    for entity_id in stale:
        assert registry.async_get(entity_id) is None


def test_enabled_presets_defaults_and_filtering() -> None:
    """Unset/malformed selections mean all; unknowns drop; order is canonical."""
    assert enabled_presets({}) == list(SELECTABLE_PRESETS)
    assert enabled_presets({CONF_PRESETS: "home"}) == list(SELECTABLE_PRESETS)
    assert enabled_presets({CONF_PRESETS: ["sleep", "bogus", "home"]}) == [
        "home",
        "sleep",
    ]
    assert enabled_presets({CONF_PRESETS: []}) == []
