"""Tests for setup and teardown of the config entry."""

from __future__ import annotations

from collections.abc import Callable

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
