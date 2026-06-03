"""Tests for setup and teardown of the config entry."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_setup_creates_entities(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Setup loads and creates the whole-home entity surface."""
    assert init_integration.state is ConfigEntryState.LOADED
    cid = init_integration.entry_id

    assert hass.states.get(entity_id_for("climate", cid)) is not None
    assert hass.states.get(entity_id_for("sensor", f"{cid}_home_avg_temperature"))
    assert hass.states.get(entity_id_for("sensor", f"{cid}_home_avg_humidity"))
    assert hass.states.get(entity_id_for("binary_sensor", f"{cid}_degraded"))


async def test_unload_entry(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The entry unloads cleanly."""
    assert await hass.config_entries.async_unload(init_integration.entry_id)
    await hass.async_block_till_done()
    assert init_integration.state is ConfigEntryState.NOT_LOADED
