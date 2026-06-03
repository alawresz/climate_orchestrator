"""End-to-end: the AC window exemption is own-room-only across real areas."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_orchestrator.const import (
    CONF_ACS,
    CONF_TRVS,
    DEFAULT_TITLE,
    DOMAIN,
)
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import AC_ENTITY, AREA_TEMP_SENSOR, TRV_ENTITY


async def _setup_two_areas(
    hass: HomeAssistant, register_entity_in_area: Callable[[str, str | None], str]
) -> tuple[MockConfigEntry, str, str]:
    """TRV in the living room, AC in the bedroom; each area has a window sensor."""
    area_reg = ar.async_get(hass)
    registry = er.async_get(hass)

    # Both rooms are warm so the AC wants to cool.
    hass.states.async_set(AREA_TEMP_SENSOR, "26.0", {"device_class": "temperature"})
    living = area_reg.async_get_or_create("Living Room")
    area_reg.async_update(living.id, temperature_entity_id=AREA_TEMP_SENSOR)

    bedroom_temp = "sensor.bedroom_temperature"
    hass.states.async_set(bedroom_temp, "26.0", {"device_class": "temperature"})
    bedroom = area_reg.async_get_or_create("Bedroom")
    area_reg.async_update(bedroom.id, temperature_entity_id=bedroom_temp)

    register_entity_in_area(TRV_ENTITY, living.id)
    register_entity_in_area(AC_ENTITY, bedroom.id)
    hass.states.async_set(TRV_ENTITY, "heat", {"hvac_modes": ["off", "heat"]})
    hass.states.async_set(
        AC_ENTITY, "off", {"hvac_modes": ["off", "cool"], "current_temperature": 26.0}
    )

    def _window(area_id: str, object_id: str) -> str:
        entry = registry.async_get_or_create(
            "binary_sensor",
            "test",
            f"u_{object_id}",
            suggested_object_id=object_id,
            original_device_class="window",
        )
        registry.async_update_entity(entry.entity_id, area_id=area_id)
        hass.states.async_set(entry.entity_id, "off")
        return entry.entity_id

    living_window = _window(living.id, "living_window")
    bedroom_window = _window(bedroom.id, "bedroom_window")

    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_TITLE,
        data={CONF_TRVS: [TRV_ENTITY], CONF_ACS: [AC_ENTITY]},
        entry_id="sc_two_areas",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry, living_window, bedroom_window


async def test_ac_window_exemption_is_own_room_only(
    hass: HomeAssistant,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """With the exemption on, the AC ignores its own room's window but still
    stops when a window opens in another room."""
    entry, living_window, bedroom_window = await _setup_two_areas(
        hass, register_entity_in_area
    )
    cid = entry.entry_id
    coordinator: SmartClimateCoordinator = entry.runtime_data

    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {ATTR_ENTITY_ID: entity_id_for("climate", cid), "hvac_mode": "heat_cool"},
        blocking=True,
    )
    await hass.services.async_call(
        "switch",
        "turn_on",
        {ATTR_ENTITY_ID: entity_id_for("switch", f"{cid}_ac_ignore_window")},
        blocking=True,
    )

    ac_action = entity_id_for("sensor", f"{cid}_{AC_ENTITY}_device_action")

    # Only the AC's own (bedroom) window is open -> it keeps cooling.
    hass.states.async_set(bedroom_window, "on")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ac_action).state == "cooling"

    # A window also opens in another room (living) -> the AC stands down.
    hass.states.async_set(living_window, "on")
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(ac_action).state == "idle"
