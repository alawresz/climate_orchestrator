"""Single-purpose setups: heat-only (TRVs) and cool-only (AC) adapt the entity."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.components.climate import ClimateEntityFeature
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_orchestrator.const import (
    CONF_ACS,
    CONF_TRVS,
    DEFAULT_TITLE,
    DOMAIN,
)
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import AC_ENTITY, AREA_TEMP_SENSOR, TRV_ENTITY


async def test_heating_only_is_a_single_setpoint_heat_thermostat(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A TRV-only setup exposes heat/off with one setpoint and never cools."""
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(
        TRV_ENTITY, "heat", {"hvac_modes": ["off", "heat"], "current_temperature": 17.0}
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_TITLE,
        data={CONF_TRVS: [TRV_ENTITY]},  # no ACs
        entry_id="sc_heat_only",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    cid = entry.entry_id
    climate = entity_id_for("climate", cid)
    coordinator: SmartClimateCoordinator = entry.runtime_data

    state = hass.states.get(climate)
    assert state.attributes["hvac_modes"] == ["off", "heat"]
    features = state.attributes["supported_features"]
    assert features & ClimateEntityFeature.TARGET_TEMPERATURE
    assert not features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
    assert not features & ClimateEntityFeature.FAN_MODE
    # One setpoint, not a range.
    assert "temperature" in state.attributes
    assert "target_temp_low" not in state.attributes

    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {ATTR_ENTITY_ID: climate, "hvac_mode": "heat"},
        blocking=True,
    )

    hass.states.async_set(AREA_TEMP_SENSOR, "17.0", {"device_class": "temperature"})
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(climate).attributes["hvac_action"] == "heating"

    hass.states.async_set(AREA_TEMP_SENSOR, "30.0", {"device_class": "temperature"})
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(climate).attributes["hvac_action"] == "idle"


async def test_cooling_only_is_a_single_setpoint_cool_thermostat(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """An AC-only setup exposes cool/off with one setpoint and never heats."""
    register_entity_in_area(AC_ENTITY, living_area)
    hass.states.async_set(
        AC_ENTITY, "off", {"hvac_modes": ["off", "cool"], "current_temperature": 26.0}
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_TITLE,
        data={CONF_ACS: [AC_ENTITY]},  # no TRVs
        entry_id="sc_cool_only",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    cid = entry.entry_id
    climate = entity_id_for("climate", cid)
    coordinator: SmartClimateCoordinator = entry.runtime_data

    state = hass.states.get(climate)
    assert state.attributes["hvac_modes"] == ["off", "cool"]
    features = state.attributes["supported_features"]
    assert features & ClimateEntityFeature.TARGET_TEMPERATURE
    assert not features & ClimateEntityFeature.TARGET_TEMPERATURE_RANGE

    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {ATTR_ENTITY_ID: climate, "hvac_mode": "cool"},
        blocking=True,
    )

    # Hot room -> the AC cools.
    hass.states.async_set(AREA_TEMP_SENSOR, "30.0", {"device_class": "temperature"})
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(climate).attributes["hvac_action"] == "cooling"

    # Cold room -> nothing heats (there is no heater); it idles.
    hass.states.async_set(AREA_TEMP_SENSOR, "15.0", {"device_class": "temperature"})
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(climate).attributes["hvac_action"] == "idle"
