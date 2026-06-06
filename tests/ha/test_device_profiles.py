"""Resolving a device's profile through the Home Assistant device registry."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_orchestrator.devices.profiles import (
    GENERIC,
    SONOFF_TRVZB,
    profile_for_entity,
)


def _climate_on_device(
    hass: HomeAssistant, *, manufacturer: str | None, model: str | None
) -> str:
    """Register a climate entity on a device with the given make/model."""
    entry = MockConfigEntry(domain="test")
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("test", f"{manufacturer}-{model}")},
        manufacturer=manufacturer,
        model=model,
    )
    climate = er.async_get(hass).async_get_or_create(
        "climate",
        "test",
        "u_profiled",
        suggested_object_id="profiled",
        device_id=device.id,
    )
    return climate.entity_id


async def test_unknown_hardware_resolves_to_generic(hass: HomeAssistant) -> None:
    """A device with an unrecognised make/model gets the generic profile."""
    entity_id = _climate_on_device(hass, manufacturer="Acme", model="Widget")
    assert profile_for_entity(hass, entity_id) is GENERIC


async def test_sonoff_trvzb_device_resolves_to_its_profile(
    hass: HomeAssistant,
) -> None:
    """A real TRVZB device (make/model on the device) gets the SONOFF profile."""
    entity_id = _climate_on_device(hass, manufacturer="SONOFF", model="TRVZB")
    assert profile_for_entity(hass, entity_id) is SONOFF_TRVZB


async def test_entity_without_a_registry_entry_resolves_to_generic(
    hass: HomeAssistant,
) -> None:
    """A bare state with no registry entry still resolves (to generic)."""
    hass.states.async_set("climate.orphan", "heat")
    assert profile_for_entity(hass, "climate.orphan") is GENERIC


async def test_entity_without_a_device_resolves_to_generic(
    hass: HomeAssistant,
) -> None:
    """A registered entity with no backing device resolves to generic."""
    climate = er.async_get(hass).async_get_or_create(
        "climate", "test", "u_no_device", suggested_object_id="no_device"
    )
    assert profile_for_entity(hass, climate.entity_id) is GENERIC
