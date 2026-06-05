"""Tri-state status + startup repair suppression.

Right after a Home Assistant restart, managed devices and their area sensors
often haven't reported in yet. The orchestrator reports ``initializing`` during
a warm-up window — until a usable reading arrives *and* every managed device
has reported in — and holds back the transient ``no_temperature_source`` repair
and the degraded notification. If the window elapses with something still
missing, it goes ``degraded`` (and the repair fires), because the gap is then
real.
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
)
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import AREA_HUMIDITY_SENSOR, AREA_TEMP_SENSOR, TRV_ENTITY
from tests.ha.helpers import (
    expire_startup_grace,
)


async def test_unavailable_device_after_warmup_is_degraded(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A device that reported in and then went away is degraded — even inside
    the grace window — and is listed in the ``unavailable_devices`` attribute."""
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


async def _setup_with_joining_device(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> MockConfigEntry:
    """Set up a TRV-only entry where the sensors beat the device to startup."""
    register_entity_in_area(TRV_ENTITY, living_area)
    # The area sensor (live via the living_area fixture) reports immediately;
    # the TRV is still joining.
    hass.states.async_set(TRV_ENTITY, STATE_UNAVAILABLE)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_TITLE,
        data={CONF_TRVS: [TRV_ENTITY]},
        entry_id="sc_status_join",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_joining_device_keeps_initializing_not_degraded(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A usable reading with a never-seen device stays initializing — no
    degraded flash (or notification) while devices are still joining."""
    entry = await _setup_with_joining_device(hass, living_area, register_entity_in_area)
    status_eid = entity_id_for("sensor", f"{entry.entry_id}_status")
    assert hass.states.get(status_eid).state == "initializing"
    notification_id = f"climate_orchestrator_{entry.entry_id}_degraded"
    assert notification_id not in hass.data.get("persistent_notification", {})

    # The TRV reports in: warm-up complete, straight to ok.
    hass.states.async_set(TRV_ENTITY, "heat", {"hvac_modes": ["off", "heat"]})
    coordinator: SmartClimateCoordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get(status_eid).state == "ok"


async def test_device_never_joining_is_degraded_after_grace(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """The grace window elapsing with a device still missing is a real fault."""
    entry = await _setup_with_joining_device(hass, living_area, register_entity_in_area)
    coordinator: SmartClimateCoordinator = entry.runtime_data

    expire_startup_grace(coordinator)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    status = hass.states.get(entity_id_for("sensor", f"{entry.entry_id}_status"))
    assert status.state == "degraded"
    assert TRV_ENTITY in status.attributes["unavailable_devices"]


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
    expire_startup_grace(coordinator)
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert (
        ir.async_get(hass).async_get_issue(DOMAIN, "no_temperature_source") is not None
    )
    status = hass.states.get(entity_id_for("sensor", f"{entry.entry_id}_status"))
    assert status.state == "degraded"
