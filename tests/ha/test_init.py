"""Tests for setup and teardown of the config entry."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
from unittest.mock import patch

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_orchestrator import async_migrate_entry
from custom_components.climate_orchestrator.const import (
    CONF_TRVS,
    CONFIG_ENTRY_VERSION,
    DEFAULT_TITLE,
    DOMAIN,
)
from custom_components.climate_orchestrator.control.mpc.controller import (
    MpcController,
)
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import TRV_ENTITY
from tests.ha.helpers import (
    mpc_payload,
    mpc_store,
    runtime,
    spawn_background,
    state_payload,
    state_store,
)


async def test_setup_creates_entities(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Setup loads and creates the whole-home entity surface."""
    assert init_integration.state is ConfigEntryState.LOADED
    cid = init_integration.entry_id

    climate = hass.states.get(entity_id_for("climate", cid))
    assert climate is not None
    # A valid MDI icon name, so the frontend actually renders one.
    assert climate.attributes.get("icon") == "mdi:thermostat"
    assert hass.states.get(entity_id_for("sensor", f"{cid}_home_avg_temperature"))
    assert hass.states.get(entity_id_for("sensor", f"{cid}_home_avg_humidity"))
    assert hass.states.get(entity_id_for("sensor", f"{cid}_status"))


async def test_setup_prunes_retired_entities(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> None:
    """Registry entries for retired unique_ids are removed at setup.

    The per-TRV MPC gain/loss/error sensors were folded into the
    learning-status sensor's attributes; an upgrade must not leave their
    registry entries behind as unavailable orphans.
    """
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat")
    config_entry.add_to_hass(hass)

    registry = er.async_get(hass)
    cid = config_entry.entry_id
    retired = [
        registry.async_get_or_create(
            "sensor",
            DOMAIN,
            f"{cid}_{TRV_ENTITY}_{suffix}",
            config_entry=config_entry,
        ).entity_id
        for suffix in ("mpc_heating_gain", "mpc_heat_loss", "mpc_model_error")
    ]
    kept = registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{cid}_{TRV_ENTITY}_mpc_learning_status",
        config_entry=config_entry,
    ).entity_id

    assert await hass.config_entries.async_setup(cid)
    await hass.async_block_till_done()

    for entity_id in retired:
        assert registry.async_get(entity_id) is None
    assert registry.async_get(kept) is not None


async def test_unload_entry(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The entry unloads cleanly."""
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED


async def test_failed_platform_unload_keeps_the_entry_loaded(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """If the platforms refuse to unload, the coordinator isn't shut down.

    Tearing the coordinator down under still-loaded platforms would leave
    their entities pointing at a dead coordinator.
    """
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    with patch(
        "homeassistant.config_entries.ConfigEntries.async_unload_platforms",
        return_value=False,
    ):
        assert not await hass.config_entries.async_unload(init_integration.entry_id)
    assert init_integration.state is ConfigEntryState.FAILED_UNLOAD
    # The coordinator deliberately kept running (the platforms still hold it);
    # stop it by hand so the test doesn't leave its refresh timer behind.
    await coordinator.async_shutdown()


async def test_entry_without_devices_is_inert_but_healthy(
    hass: HomeAssistant,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A config selecting no devices sets up and reports OK, not degraded.

    With nothing managed there is nothing to warm up or supervise; the entity
    surface exists and simply does nothing.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_TITLE,
        data={CONF_TRVS: []},
        entry_id="sc_empty",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    status = hass.states.get(entity_id_for("sensor", f"{entry.entry_id}_status"))
    assert status.state == "ok"


async def test_migration_passes_current_version_through(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    """A current-version entry migrates as a no-op and sets up normally."""
    config_entry.add_to_hass(hass)
    assert await async_migrate_entry(hass, config_entry)
    assert config_entry.version == CONFIG_ENTRY_VERSION


async def test_migration_refuses_entries_from_the_future(
    hass: HomeAssistant,
) -> None:
    """A newer-major entry (downgrade scenario) is refused, not mis-read."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_TITLE,
        data={CONF_TRVS: [TRV_ENTITY]},
        version=CONFIG_ENTRY_VERSION + 1,
    )
    entry.add_to_hass(hass)
    assert not await async_migrate_entry(hass, entry)


async def test_remove_entry_cleans_persisted_stores(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    hass_storage: dict[str, Any],
) -> None:
    """Deleting the entry removes the learned-state .storage files."""
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    runtime(coordinator, TRV_ENTITY).mpc = MpcController()
    await mpc_store(coordinator).async_save(mpc_payload(coordinator))
    await state_store(coordinator).async_save(state_payload(coordinator))
    cid = init_integration.entry_id
    assert f"climate_orchestrator.{cid}.mpc" in hass_storage
    assert f"climate_orchestrator.{cid}.maintenance" in hass_storage

    await hass.config_entries.async_remove(cid)
    await hass.async_block_till_done()

    assert f"climate_orchestrator.{cid}.mpc" not in hass_storage
    assert f"climate_orchestrator.{cid}.maintenance" not in hass_storage


async def test_background_tasks_are_cancelled_on_unload(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Fire-and-forget work (store saves, auto maintenance) dies with the entry.

    A bare ``hass.async_create_task`` would keep running after unload
    (use-after-unload); everything must go through the entry-tracked helper.
    """
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def _hang() -> None:
        started.set()
        try:
            await asyncio.sleep(60)
        except asyncio.CancelledError:
            cancelled.set()
            raise

    spawn_background(coordinator, _hang(), "test hang")
    await started.wait()

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert cancelled.is_set()
