"""End-to-end integration tests: sensors -> coordinator -> engine -> devices.

These drive the real coordinator with faked desired state and managed-device
states, and assert the actual `climate.*` service calls it issues. Climate
services are mocked to capture (and harmlessly absorb) those calls.

NOTE: the mock `climate.*` services must be registered *after* the integration
is set up — setting up the climate platform (re)registers the real climate
services, which would otherwise clobber an earlier mock.
"""

from __future__ import annotations

from collections.abc import Callable
import time

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.components.number import (
    DOMAIN as NUMBER_DOMAIN,
)
from homeassistant.components.number import (
    SERVICE_SET_VALUE,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_mock_service,
)

from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import AC_ENTITY, AREA_TEMP_SENSOR, TRV_ENTITY

_HEAT_ATTRS = {
    "hvac_modes": ["off", "heat"],
    "min_temp": 7,
    "max_temp": 35,
    "target_temp_step": 0.5,
}
_COOL_ATTRS = {
    "hvac_modes": ["off", "cool", "dry"],
    "min_temp": 16,
    "max_temp": 30,
    "target_temp_step": 0.5,
}


def _commanded(
    calls: list[ServiceCall], entity_id: str, key: str, value: object
) -> bool:
    return any(
        call.data[ATTR_ENTITY_ID] == entity_id and call.data.get(key) == value
        for call in calls
    )


def _mock_climate_services(
    hass: HomeAssistant,
) -> tuple[list[ServiceCall], list[ServiceCall]]:
    """Mock the climate write services (call *after* integration setup)."""
    set_hvac = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_HVAC_MODE)
    set_temp = async_mock_service(hass, CLIMATE_DOMAIN, SERVICE_SET_TEMPERATURE)
    return set_hvac, set_temp


async def _drive(
    hass: HomeAssistant,
    coordinator: SmartClimateCoordinator,
    climate_id: str,
    *,
    low: float = 20.5,
    high: float = 24.5,
) -> None:
    """Fake the whole-home entity ON with a band, then run a control cycle."""
    hass.states.async_set(
        climate_id,
        "heat_cool",
        {"target_temp_low": low, "target_temp_high": high, "preset_mode": "manual"},
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()


async def _setup_living(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    area_id: str,
    register: Callable[[str, str | None], str],
) -> None:
    register(TRV_ENTITY, area_id)
    register(AC_ENTITY, area_id)
    hass.states.async_set(TRV_ENTITY, "off", _HEAT_ATTRS)
    hass.states.async_set(AC_ENTITY, "off", _COOL_ATTRS)
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()


async def test_cold_room_commands_trv_to_heat(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A cold area drives its TRV to heat toward the band target."""
    await _setup_living(hass, config_entry, living_area, register_entity_in_area)
    set_hvac, set_temp = _mock_climate_services(hass)

    hass.states.async_set(AREA_TEMP_SENSOR, "17.0")
    climate_id = entity_id_for("climate", config_entry.entry_id)
    await _drive(hass, config_entry.runtime_data, climate_id)

    assert _commanded(set_hvac, TRV_ENTITY, ATTR_HVAC_MODE, "heat")
    # heat target = heat_edge 20.5 + tolerance 0.3 = 20.8, snapped to 0.5 -> 21.0
    assert _commanded(set_temp, TRV_ENTITY, ATTR_TEMPERATURE, 21.0)


async def test_hot_room_commands_ac_to_cool_with_bias(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A hot area drives the AC to cool, biased below the real target."""
    await _setup_living(hass, config_entry, living_area, register_entity_in_area)
    set_hvac, set_temp = _mock_climate_services(hass)

    hass.states.async_set(AREA_TEMP_SENSOR, "27.0")
    climate_id = entity_id_for("climate", config_entry.entry_id)
    await _drive(hass, config_entry.runtime_data, climate_id)

    assert _commanded(set_hvac, AC_ENTITY, ATTR_HVAC_MODE, "cool")
    # cool target (24.5 - 0.3 = 24.2) - base bias 1.5 = 22.7, snapped to 0.5 -> 22.5
    assert _commanded(set_temp, AC_ENTITY, ATTR_TEMPERATURE, 22.5)


async def test_home_average_engages_a_comfortable_rooms_ac(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A hot bedroom lifts the home average, engaging the living-room AC."""
    bedroom_temp = "sensor.bedroom2_temperature"
    hass.states.async_set(bedroom_temp, "30.0", {"device_class": "temperature"})
    area_reg = ar.async_get(hass)
    bedroom = area_reg.async_get_or_create("Bedroom 2")
    area_reg.async_update(bedroom.id, temperature_entity_id=bedroom_temp)

    register_entity_in_area(AC_ENTITY, living_area)
    register_entity_in_area(TRV_ENTITY, bedroom.id)
    hass.states.async_set(AC_ENTITY, "off", _COOL_ATTRS)
    hass.states.async_set(TRV_ENTITY, "off", _HEAT_ATTRS)
    hass.states.async_set(AREA_TEMP_SENSOR, "22.0")  # living is comfortable
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    set_hvac, _ = _mock_climate_services(hass)
    climate_id = entity_id_for("climate", config_entry.entry_id)
    await _drive(hass, config_entry.runtime_data, climate_id)

    # Living is at 22 (below the cool edge) but the home average (≈26) is over it,
    # so the AC engages via the OR-trigger.
    assert _commanded(set_hvac, AC_ENTITY, ATTR_HVAC_MODE, "cool")


async def test_open_window_suppresses_heating(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """An open window in the area stops the TRV heating."""
    await _setup_living(hass, config_entry, living_area, register_entity_in_area)
    set_hvac, _ = _mock_climate_services(hass)

    registry = er.async_get(hass)
    window = registry.async_get_or_create(
        "binary_sensor",
        "test",
        "u_window",
        suggested_object_id="living_window",
        original_device_class="window",
    )
    registry.async_update_entity(window.entity_id, area_id=living_area)
    hass.states.async_set(window.entity_id, "on")
    hass.states.async_set(AREA_TEMP_SENSOR, "17.0")  # cold enough to heat

    climate_id = entity_id_for("climate", config_entry.entry_id)
    await _drive(hass, config_entry.runtime_data, climate_id)

    assert not _commanded(set_hvac, TRV_ENTITY, ATTR_HVAC_MODE, "heat")


async def test_frost_protection_overrides_open_window(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Below the frost temperature, the TRV heats even with the window open."""
    await _setup_living(hass, config_entry, living_area, register_entity_in_area)
    set_hvac, _ = _mock_climate_services(hass)

    registry = er.async_get(hass)
    window = registry.async_get_or_create(
        "binary_sensor",
        "test",
        "u_window",
        suggested_object_id="living_window",
        original_device_class="window",
    )
    registry.async_update_entity(window.entity_id, area_id=living_area)
    hass.states.async_set(window.entity_id, "on")
    hass.states.async_set(AREA_TEMP_SENSOR, "5.0")  # below frost protection temp

    climate_id = entity_id_for("climate", config_entry.entry_id)
    await _drive(hass, config_entry.runtime_data, climate_id)

    assert _commanded(set_hvac, TRV_ENTITY, ATTR_HVAC_MODE, "heat")


async def test_window_open_delay_defers_then_stops_heating(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """With a delay set, an opened window keeps heating until the delay elapses."""
    await _setup_living(hass, config_entry, living_area, register_entity_in_area)

    # A 10-minute grace period before an open window stops heating.
    await hass.services.async_call(
        NUMBER_DOMAIN,
        SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: entity_id_for(
                "number", f"{config_entry.entry_id}_window_open_delay"
            ),
            "value": 10.0,
        },
        blocking=True,
    )

    set_hvac, _ = _mock_climate_services(hass)
    registry = er.async_get(hass)
    window = registry.async_get_or_create(
        "binary_sensor",
        "test",
        "u_window",
        suggested_object_id="living_window",
        original_device_class="window",
    )
    registry.async_update_entity(window.entity_id, area_id=living_area)
    hass.states.async_set(window.entity_id, "on")
    hass.states.async_set(AREA_TEMP_SENSOR, "17.0")  # cold enough to heat

    climate_id = entity_id_for("climate", config_entry.entry_id)
    coordinator: SmartClimateCoordinator = config_entry.runtime_data

    # Window just opened: within the grace period, heating continues.
    await _drive(hass, coordinator, climate_id)
    assert _commanded(set_hvac, TRV_ENTITY, ATTR_HVAC_MODE, "heat")

    # Pretend the window has now been open longer than the delay, and re-run.
    set_hvac.clear()
    coordinator._window_open_since[living_area] = time.monotonic() - 999.0
    await _drive(hass, coordinator, climate_id)
    assert not _commanded(set_hvac, TRV_ENTITY, ATTR_HVAC_MODE, "heat")


async def test_adaptive_ac_bias_lowers_the_setpoint(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A learned bias add-on (on by default) deepens the AC setpoint offset."""
    await _setup_living(hass, config_entry, living_area, register_entity_in_area)
    _, set_temp = _mock_climate_services(hass)

    coordinator: SmartClimateCoordinator = config_entry.runtime_data
    coordinator._ac_bias_integral[AC_ENTITY] = 1.0  # learned extra bias
    hass.states.async_set(AREA_TEMP_SENSOR, "27.0")
    climate_id = entity_id_for("climate", config_entry.entry_id)
    await _drive(hass, coordinator, climate_id)

    # cool target 24.2 - (base 1.5 + learned 1.0) = 21.7, snapped to 0.5 -> 21.5
    assert _commanded(set_temp, AC_ENTITY, ATTR_TEMPERATURE, 21.5)
