"""Tests for the calibration-mode select."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.const import ATTR_ENTITY_ID, EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_calibration_mode_defaults_to_target(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """The calibration mode defaults to the safe 'target' strategy."""
    entity_id = entity_id_for("select", f"{init_integration.entry_id}_calibration_mode")
    assert hass.states.get(entity_id).state == "target"


async def test_select_calibration_mode(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Selecting a different mode updates the state."""
    entity_id = entity_id_for("select", f"{init_integration.entry_id}_calibration_mode")
    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": "mpc"},
        blocking=True,
    )
    assert hass.states.get(entity_id).state == "mpc"


async def test_calibration_mode_is_a_control_not_config(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """The calibration select sits in Controls (no entity category)."""
    registry = er.async_get(hass)
    cid = init_integration.entry_id
    select = entity_id_for("select", f"{cid}_calibration_mode")
    switch = entity_id_for("switch", f"{cid}_frost_protection")
    assert registry.async_get(select).entity_category is None
    assert registry.async_get(switch).entity_category is EntityCategory.CONFIG
