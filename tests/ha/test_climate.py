"""Tests for the whole-home climate entity."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.climate import (
    ATTR_HVAC_ACTION,
    ATTR_HVAC_MODE,
    ATTR_PRESET_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant, State
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache,
)

from custom_components.climate_orchestrator.const import (
    CONF_TRVS,
    DEFAULT_PRESETS,
    DEFAULT_TITLE,
    DOMAIN,
)
from custom_components.climate_orchestrator.control.comfort import apparent_temperature
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import AC_ENTITY, AREA_HUMIDITY_SENSOR, AREA_TEMP_SENSOR, TRV_ENTITY
from tests.ha.helpers import (
    set_rmot,
)


@pytest.fixture
def climate_id(
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> str:
    """The whole-home climate entity_id (unique_id == entry_id)."""
    return entity_id_for("climate", init_integration.entry_id)


async def test_reports_home_averages(hass: HomeAssistant, climate_id: str) -> None:
    """Current temperature is the feels-like value (comfort targeting on by
    default); the raw dry-bulb average is kept as an attribute."""
    state = hass.states.get(climate_id)
    assert state is not None
    # Comfort index targeting is on by default -> apparent (feels-like) temp.
    # The entity rounds current_temperature to 0.1 deg for display.
    assert state.attributes["current_temperature"] == pytest.approx(
        apparent_temperature(21.0, 45.0), abs=0.05
    )
    assert state.attributes["dry_bulb_temperature"] == 21.0
    assert state.attributes["current_humidity"] == 45.0


async def test_current_temperature_is_dry_bulb_without_comfort(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    climate_id: str,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """With comfort index targeting off, current temp is the dry-bulb average."""
    cid = init_integration.entry_id
    await hass.services.async_call(
        "switch",
        "turn_off",
        {ATTR_ENTITY_ID: entity_id_for("switch", f"{cid}_comfort_index_targeting")},
        blocking=True,
    )
    state = hass.states.get(climate_id)
    assert state.attributes["current_temperature"] == 21.0


async def test_adaptive_comfort_relaxes_displayed_cool_edge(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    climate_id: str,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """With adaptive comfort on and a hot running-mean, the high handle shows the
    relaxed cool edge while the base band stays in its attribute."""
    cid = init_integration.entry_id
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    set_rmot(coordinator, 30.0)  # above onset (cool edge + bias)

    await hass.services.async_call(
        "switch",
        "turn_on",
        {ATTR_ENTITY_ID: entity_id_for("switch", f"{cid}_adaptive_cooling_comfort")},
        blocking=True,
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(climate_id)
    base_high = state.attributes["base_target_temp_high"]
    # Displayed cool edge is relaxed above the user-set base; heat edge unmoved.
    assert state.attributes["target_temp_high"] > base_high
    assert (
        state.attributes["target_temp_low"] == state.attributes["base_target_temp_low"]
    )


async def test_set_band_switches_to_manual(
    hass: HomeAssistant, climate_id: str
) -> None:
    """Setting the two setpoints moves the preset to 'manual'."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {
            ATTR_ENTITY_ID: climate_id,
            ATTR_TARGET_TEMP_LOW: 19.0,
            ATTR_TARGET_TEMP_HIGH: 24.0,
        },
        blocking=True,
    )
    state = hass.states.get(climate_id)
    assert state.attributes["target_temp_low"] == 19.0
    assert state.attributes["target_temp_high"] == 24.0
    assert state.attributes[ATTR_PRESET_MODE] == "manual"


async def test_set_preset_applies_band_edges(
    hass: HomeAssistant, climate_id: str
) -> None:
    """Selecting a preset applies its two band edges as the setpoints."""
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: climate_id, ATTR_PRESET_MODE: "sleep"},
        blocking=True,
    )
    state = hass.states.get(climate_id)
    low, high = DEFAULT_PRESETS["sleep"]
    assert state.attributes["target_temp_low"] == low
    assert state.attributes["target_temp_high"] == high


async def test_hvac_action_off_idle_off(hass: HomeAssistant, climate_id: str) -> None:
    """Defaults to OFF; HEAT_COOL is IDLE in a neutral room; off again."""
    state = hass.states.get(climate_id)
    assert state.state == HVACMode.OFF
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.OFF

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_HVAC_MODE,
        {ATTR_ENTITY_ID: climate_id, ATTR_HVAC_MODE: HVACMode.HEAT_COOL},
        blocking=True,
    )
    state = hass.states.get(climate_id)
    assert state.state == HVACMode.HEAT_COOL
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.IDLE

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: climate_id},
        blocking=True,
    )
    state = hass.states.get(climate_id)
    assert state.state == HVACMode.OFF
    assert state.attributes[ATTR_HVAC_ACTION] == HVACAction.OFF


async def test_restores_mode_and_preset_across_restart(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> None:
    """After a restart the entity comes back in its previous mode/preset."""
    register_entity_in_area(TRV_ENTITY, living_area)
    register_entity_in_area(AC_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "off")
    hass.states.async_set(AC_ENTITY, "off")
    # Seed the state the entity had before the (simulated) restart.
    mock_restore_cache(
        hass,
        [
            State(
                "climate.climate_orchestrator",
                HVACMode.HEAT_COOL,
                {"preset_mode": "sleep"},
            )
        ],
    )

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("climate.climate_orchestrator")
    assert state.state == HVACMode.HEAT_COOL  # not reset to OFF
    assert state.attributes[ATTR_PRESET_MODE] == "sleep"


async def test_restores_single_setpoint_manual_band(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A heat-only entity restores its one manual setpoint, not a band.

    Single-setpoint hardware persists ``temperature`` (no low/high pair); the
    restore path must map it back onto the edge the hardware actually uses.
    """
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat", {"hvac_modes": ["off", "heat"]})
    mock_restore_cache(
        hass,
        [
            State(
                "climate.climate_orchestrator",
                HVACMode.HEAT,
                {"preset_mode": "manual", "temperature": 19.5},
            )
        ],
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_TITLE,
        data={CONF_TRVS: [TRV_ENTITY]},  # no ACs: single heat setpoint
        entry_id="sc_manual_single",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id_for("climate", entry.entry_id))
    assert state.attributes[ATTR_PRESET_MODE] == "manual"
    assert state.attributes["temperature"] == 19.5


async def test_stays_available_when_one_device_drops(
    hass: HomeAssistant, init_integration: MockConfigEntry, climate_id: str
) -> None:
    """One device dropping does not take the whole-home entity down."""
    hass.states.async_set(TRV_ENTITY, STATE_UNAVAILABLE)
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(climate_id).state != STATE_UNAVAILABLE


async def test_unavailable_only_when_everything_gone(
    hass: HomeAssistant, init_integration: MockConfigEntry, climate_id: str
) -> None:
    """The entity goes unavailable only when no device or temp source remains."""
    for entity in (TRV_ENTITY, AC_ENTITY, AREA_TEMP_SENSOR, AREA_HUMIDITY_SENSOR):
        hass.states.async_set(entity, STATE_UNAVAILABLE)
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(climate_id).state == STATE_UNAVAILABLE


async def test_unavailable_when_the_coordinator_update_fails(
    hass: HomeAssistant, init_integration: MockConfigEntry, climate_id: str
) -> None:
    """A failed coordinator update takes the entity unavailable, and back."""
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    coordinator.async_set_update_error(RuntimeError("update failed"))
    await hass.async_block_till_done()
    assert hass.states.get(climate_id).state == STATE_UNAVAILABLE

    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(climate_id).state != STATE_UNAVAILABLE


async def test_turn_on_enters_the_supported_mode(
    hass: HomeAssistant, climate_id: str
) -> None:
    """climate.turn_on lands in the hardware's on-mode, not a guess."""
    assert hass.states.get(climate_id).state == HVACMode.OFF
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: climate_id},
        blocking=True,
    )
    assert hass.states.get(climate_id).state == HVACMode.HEAT_COOL
