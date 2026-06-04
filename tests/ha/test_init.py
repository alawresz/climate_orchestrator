"""Tests for setup and teardown of the config entry."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
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


async def test_unload_entry(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The entry unloads cleanly."""
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED


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
    coordinator._runtime(TRV_ENTITY).mpc = MpcController()
    await coordinator._mpc_store.async_save(coordinator._mpc_persist_data())
    await coordinator._maint_store.async_save(coordinator._state_persist_data())
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

    coordinator._background(_hang(), "test hang")
    await started.wait()

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert cancelled.is_set()
