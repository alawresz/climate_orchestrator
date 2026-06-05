"""Hass fixtures for the Home Assistant-facing tests (tests/ha/)."""

from __future__ import annotations

from collections.abc import Callable, Generator
from unittest.mock import PropertyMock, patch

from homeassistant.core import HomeAssistant
from homeassistant.helpers import area_registry as ar
from homeassistant.helpers import entity_registry as er
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_orchestrator.const import (
    CONF_ACS,
    CONF_TRVS,
    DEFAULT_TITLE,
    DOMAIN,
)
from tests.conftest import (
    AC_ENTITY,
    AREA_HUMIDITY_SENSOR,
    AREA_TEMP_SENSOR,
    TRV_ENTITY,
)


@pytest.fixture(autouse=True)
def auto_enable_disabled_entities() -> Generator[None]:
    """Create default-disabled entities (runtime/cycle counters) in tests.

    Inlined from HA core's ``entity_registry_enabled_by_default`` fixture
    (tests/components/conftest.py), which PHACC does not ship.
    """
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        return_value=True,
        new_callable=PropertyMock,
    ):
        yield


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(
    enable_custom_integrations: None,  # noqa: ARG001 - fixture wired by name
) -> None:
    """Enable loading of custom integrations in every test."""
    return


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A config entry selecting one TRV and one AC."""
    return MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_TITLE,
        data={CONF_TRVS: [TRV_ENTITY], CONF_ACS: [AC_ENTITY]},
        entry_id="sc_test",
    )


@pytest.fixture
def living_area(hass: HomeAssistant) -> str:
    """Create a 'Living Room' area with configured temp/humidity sensors.

    HA's area registry validates that the sensors exist (and have the right
    device class) when they are assigned, so the states must be created first.
    """
    hass.states.async_set(AREA_TEMP_SENSOR, "21.0", {"device_class": "temperature"})
    hass.states.async_set(AREA_HUMIDITY_SENSOR, "45", {"device_class": "humidity"})
    area_reg = ar.async_get(hass)
    area = area_reg.async_get_or_create("Living Room")
    area_reg.async_update(
        area.id,
        temperature_entity_id=AREA_TEMP_SENSOR,
        humidity_entity_id=AREA_HUMIDITY_SENSOR,
    )
    return area.id


@pytest.fixture
def entity_id_for(hass: HomeAssistant) -> Callable[[str, str], str]:
    """Resolve an entity_id by platform + unique_id (avoids slug guessing)."""

    def _get(platform: str, unique_id: str) -> str:
        entity_id = er.async_get(hass).async_get_entity_id(platform, DOMAIN, unique_id)
        assert entity_id is not None, f"no entity for {platform}/{unique_id}"
        return entity_id

    return _get


@pytest.fixture
def register_entity_in_area(
    hass: HomeAssistant,
) -> Callable[[str, str | None], str]:
    """Return a helper that registers an entity (optionally in an area)."""

    def _register(entity_id: str, area_id: str | None) -> str:
        domain, object_id = entity_id.split(".", 1)
        ent_reg = er.async_get(hass)
        entry = ent_reg.async_get_or_create(
            domain, "test", f"unique_{object_id}", suggested_object_id=object_id
        )
        if area_id is not None:
            ent_reg.async_update_entity(entry.entity_id, area_id=area_id)
        return entry.entity_id

    return _register


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
) -> MockConfigEntry:
    """Set up the integration with one TRV + one AC in the living room."""
    register_entity_in_area(TRV_ENTITY, living_area)
    register_entity_in_area(AC_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat")
    hass.states.async_set(AC_ENTITY, "off")
    # Area sensors are created by the `living_area` fixture (21.0 / 45).

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
