"""Tests for the TRV local-offset helper and number discovery."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_orchestrator.devices.trv import (
    find_related_number,
    local_offset,
)


def test_offset_makes_trv_track_area() -> None:
    """Offset = area - internal, so the TRV behaves as if it read the area."""
    assert local_offset(21.0, 19.5) == 1.5


def test_offset_none_when_data_missing() -> None:
    """Missing either temperature yields no offset."""
    assert local_offset(None, 20.0) is None
    assert local_offset(21.0, None) is None


def test_offset_is_clamped() -> None:
    """A wild delta is clamped to the safe range."""
    assert local_offset(40.0, 5.0) == 10.0


async def test_find_related_number_honours_custom_hints(hass: HomeAssistant) -> None:
    """Discovery matches a non-standard valve number when given custom hints."""
    entry = MockConfigEntry(domain="climate_orchestrator")
    entry.add_to_hass(hass)
    device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, identifiers={("trv_test", "trv")}
    )
    registry = er.async_get(hass)
    climate = registry.async_get_or_create(
        "climate", "trv_test", "u_climate", device_id=device.id
    )
    number = registry.async_get_or_create(
        "number",
        "trv_test",
        "u_number",
        suggested_object_id="oddbrand_valve_pos",
        device_id=device.id,
    )

    # The default Zigbee2MQTT hints don't match this brand's naming.
    assert (
        find_related_number(hass, climate.entity_id, ("valve_opening_degree",)) is None
    )
    # A custom hint does.
    assert (
        find_related_number(hass, climate.entity_id, ("valve_pos",)) == number.entity_id
    )
