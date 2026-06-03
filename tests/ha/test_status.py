"""Tri-state status + startup repair suppression.

Right after a Home Assistant restart, managed devices and their area sensors
often haven't reported in yet. The orchestrator reports ``initializing`` during
a warm-up window and holds back the transient ``no_temperature_source`` repair
until either a usable reading arrives (``ok``) or the window elapses with still
nothing (``degraded`` + the repair fires, because the gap is then real).
"""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_orchestrator.const import (
    CONF_TRVS,
    DEFAULT_TITLE,
    DOMAIN,
    STARTUP_GRACE_SECONDS,
)
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import AREA_HUMIDITY_SENSOR, AREA_TEMP_SENSOR, TRV_ENTITY


async def test_unavailable_device_after_warmup_is_degraded(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Once initialized, an unavailable device flips status to degraded and is
    listed in the status sensor's ``unavailable_devices`` attribute."""
    cid = init_integration.entry_id
    status_eid = entity_id_for("sensor", f"{cid}_status")
    # init_integration has a live reading at setup -> warm-up already over.
    assert hass.states.get(status_eid).state == "ok"

    hass.states.async_set(TRV_ENTITY, STATE_UNAVAILABLE)
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    state = hass.states.get(status_eid)
    assert state.state == "degraded"
    assert TRV_ENTITY in state.attributes["unavailable_devices"]


async def _setup_without_reading(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> MockConfigEntry:
    """Set up a TRV-only entry whose area sensors are unavailable at startup."""
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat", {"hvac_modes": ["off", "heat"]})
    # The area still has the sensors *assigned*, they just aren't reporting yet.
    hass.states.async_set(AREA_TEMP_SENSOR, STATE_UNAVAILABLE)
    hass.states.async_set(AREA_HUMIDITY_SENSOR, STATE_UNAVAILABLE)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_TITLE,
        data={CONF_TRVS: [TRV_ENTITY]},
        entry_id="sc_status",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_initializing_suppresses_no_temperature_repair(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """No reading yet, still within warm-up -> initializing, no repair."""
    entry = await _setup_without_reading(hass, living_area, register_entity_in_area)
    registry = ir.async_get(hass)

    assert registry.async_get_issue(DOMAIN, "no_temperature_source") is None
    status = hass.states.get(entity_id_for("sensor", f"{entry.entry_id}_status"))
    assert status.state == "initializing"


async def test_first_reading_clears_to_ok(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Once a usable reading arrives the warm-up ends -> ok, still no repair."""
    entry = await _setup_without_reading(hass, living_area, register_entity_in_area)
    coordinator: SmartClimateCoordinator = entry.runtime_data

    hass.states.async_set(AREA_TEMP_SENSOR, "20.0", {"device_class": "temperature"})
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert ir.async_get(hass).async_get_issue(DOMAIN, "no_temperature_source") is None
    status = hass.states.get(entity_id_for("sensor", f"{entry.entry_id}_status"))
    assert status.state == "ok"


async def test_degraded_after_grace_raises_repair(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Warm-up elapses with still no reading -> degraded and the repair fires."""
    entry = await _setup_without_reading(hass, living_area, register_entity_in_area)
    coordinator: SmartClimateCoordinator = entry.runtime_data

    # Pretend the warm-up window has elapsed without any usable reading.
    coordinator._started -= STARTUP_GRACE_SECONDS + 10.0
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, "no_temperature_source") is not None
    )
    status = hass.states.get(entity_id_for("sensor", f"{entry.entry_id}_status"))
    assert status.state == "degraded"
