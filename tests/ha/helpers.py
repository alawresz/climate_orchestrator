"""Shared helpers for the hass-fixture tests (plain functions, not fixtures)."""

from __future__ import annotations

from typing import Any

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_orchestrator.const import DOMAIN
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from tests.conftest import AC_ENTITY, TRV_ENTITY

# Canonical capability attributes for the fake devices (shared across suites).
TRV_ATTRS = {
    "hvac_modes": ["off", "heat"],
    "min_temp": 7.0,
    "max_temp": 35.0,
    "target_temp_step": 0.5,
}
AC_ATTRS = {
    "hvac_modes": ["off", "cool", "dry"],
    "min_temp": 16.0,
    "max_temp": 30.0,
    "target_temp_step": 0.5,
}


def set_desired_preset(
    hass: HomeAssistant,
    climate_id: str,
    mode: str = "heat_cool",
    *,
    target: float = 22.5,
) -> None:
    """Fake the whole-home entity's desired state (home preset band)."""
    hass.states.async_set(
        climate_id, mode, {"temperature": target, "preset_mode": "home"}
    )


async def select_calibration_mode(
    hass: HomeAssistant, entry_id: str, mode: str
) -> None:
    """Pick a TRV calibration mode via the select entity, as the UI would."""
    entity_id = er.async_get(hass).async_get_entity_id(
        "select", DOMAIN, f"{entry_id}_calibration_mode"
    )
    assert entity_id is not None
    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": mode},
        blocking=True,
    )


async def setup_trv_with_number(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    area_id: str,
    *,
    number_suffix: str = "valve_opening_degree",
    number_value: str = "0",
    trv_attrs: dict[str, Any] | None = None,
) -> SmartClimateCoordinator:
    """Set up the integration with a TRV exposing a related ``number`` entity.

    Registers the TRV in ``area_id`` with a device-level number entity named
    so the valve/calibration hints can discover it — the registry dance that
    used to be copy-pasted across three test files.
    """
    config_entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=config_entry.entry_id,
        identifiers={("climate_orchestrator_test", "trv1")},
    )
    registry = er.async_get(hass)
    climate = registry.async_get_or_create(
        "climate", "test", "u_trv1", suggested_object_id="trv_1", device_id=device.id
    )
    registry.async_update_entity(climate.entity_id, area_id=area_id)
    registry.async_get_or_create(
        "number",
        "test",
        f"u_{number_suffix}",
        suggested_object_id=f"trv_1_{number_suffix}",
        device_id=device.id,
    )
    hass.states.async_set(
        TRV_ENTITY, "heat", {"hvac_modes": ["off", "heat"], **(trv_attrs or {})}
    )
    hass.states.async_set(AC_ENTITY, "off")
    hass.states.async_set(f"number.trv_1_{number_suffix}", number_value)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry.runtime_data
