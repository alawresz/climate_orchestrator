"""Tests for the boost preset (directional band push with timed auto-revert)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from homeassistant.components.climate import (
    ATTR_PRESET_MODE,
    SERVICE_SET_PRESET_MODE,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, State
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_capture_events,
    async_fire_time_changed,
    mock_restore_cache,
)

from custom_components.climate_orchestrator.const import (
    BOOST_OFFSET_DEFAULT,
    CONF_PRESETS,
    DEFAULT_PRESETS,
    DOMAIN,
    EVENT_CLIMATE_ORCHESTRATOR,
    EVENT_TYPE_BOOST_ENDED,
    EVENT_TYPE_BOOST_STARTED,
)
from tests.conftest import AC_ENTITY, AREA_TEMP_SENSOR, TRV_ENTITY

_HOME_HEAT, _HOME_COOL = DEFAULT_PRESETS["home"]


def _events_of(events: list, event_type: str) -> list:
    return [e for e in events if e.data["type"] == event_type]


async def _select_preset(hass: HomeAssistant, climate_id: str, preset: str) -> None:
    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_PRESET_MODE,
        {ATTR_ENTITY_ID: climate_id, ATTR_PRESET_MODE: preset},
        blocking=True,
    )
    await hass.async_block_till_done()


async def test_boost_pushes_heat_edge_when_cold(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Below the band midpoint, boost raises the heat edge by the offset."""
    climate_id = entity_id_for("climate", init_integration.entry_id)
    await _select_preset(hass, climate_id, "boost")

    state = hass.states.get(climate_id)
    assert state.attributes[ATTR_PRESET_MODE] == "boost"
    assert state.attributes["target_temp_low"] == _HOME_HEAT + BOOST_OFFSET_DEFAULT
    assert state.attributes["target_temp_high"] == _HOME_COOL
    assert state.attributes["boost_direction"] == "heat"
    assert state.attributes["boost_previous_preset"] == "home"
    assert state.attributes["boost_until"] is not None


async def test_boost_pulls_cool_edge_when_hot(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Above the band midpoint, boost lowers the cool edge instead."""
    hass.states.async_set(AREA_TEMP_SENSOR, "27.0", {"device_class": "temperature"})
    coordinator = init_integration.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    climate_id = entity_id_for("climate", init_integration.entry_id)
    await _select_preset(hass, climate_id, "boost")

    state = hass.states.get(climate_id)
    assert state.attributes["boost_direction"] == "cool"
    assert state.attributes["target_temp_high"] == _HOME_COOL - BOOST_OFFSET_DEFAULT
    assert state.attributes["target_temp_low"] == _HOME_HEAT


async def test_boost_reverts_after_duration(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
    freezer: FrozenDateTimeFactory,
) -> None:
    """The boost runs its (default 30 min) course and reverts to the preset."""
    climate_id = entity_id_for("climate", init_integration.entry_id)
    await _select_preset(hass, climate_id, "boost")
    assert hass.states.get(climate_id).attributes[ATTR_PRESET_MODE] == "boost"

    freezer.tick(timedelta(minutes=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    state = hass.states.get(climate_id)
    assert state.attributes[ATTR_PRESET_MODE] == "home"
    assert state.attributes["target_temp_low"] == _HOME_HEAT
    assert "boost_until" not in state.attributes


async def test_manual_setpoint_cancels_boost(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Touching the setpoints ends the boost; the stale timer must not fire."""
    climate_id = entity_id_for("climate", init_integration.entry_id)
    await _select_preset(hass, climate_id, "boost")

    await hass.services.async_call(
        CLIMATE_DOMAIN,
        SERVICE_SET_TEMPERATURE,
        {
            ATTR_ENTITY_ID: climate_id,
            "target_temp_low": 19.0,
            "target_temp_high": 25.0,
        },
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get(climate_id).attributes[ATTR_PRESET_MODE] == "manual"

    freezer.tick(timedelta(minutes=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    # The cancelled timer didn't fire and flip the preset around.
    state = hass.states.get(climate_id)
    assert state.attributes[ATTR_PRESET_MODE] == "manual"
    assert state.attributes["target_temp_low"] == 19.0


async def test_selecting_a_preset_cancels_boost(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Picking a named preset mid-boost simply takes over."""
    climate_id = entity_id_for("climate", init_integration.entry_id)
    await _select_preset(hass, climate_id, "boost")
    await _select_preset(hass, climate_id, "sleep")

    state = hass.states.get(climate_id)
    assert state.attributes[ATTR_PRESET_MODE] == "sleep"
    assert "boost_until" not in state.attributes


async def test_boost_survives_restart(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A running boost is restored with its deadline and previous preset."""
    register_entity_in_area(TRV_ENTITY, living_area)
    register_entity_in_area(AC_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat")
    hass.states.async_set(AC_ENTITY, "off")
    until = dt_util.utcnow() + timedelta(minutes=10)
    mock_restore_cache(
        hass,
        [
            State(
                "climate.climate_orchestrator",
                "heat_cool",
                {
                    "preset_mode": "boost",
                    "boost_until": until.isoformat(),
                    "boost_previous_preset": "sleep",
                    "boost_direction": "heat",
                },
            )
        ],
    )

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id_for("climate", config_entry.entry_id))
    assert state.attributes[ATTR_PRESET_MODE] == "boost"
    assert state.attributes["boost_previous_preset"] == "sleep"
    sleep_heat = DEFAULT_PRESETS["sleep"][0]
    assert state.attributes["target_temp_low"] == sleep_heat + BOOST_OFFSET_DEFAULT


async def test_expired_boost_reverts_on_restart(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A boost whose deadline passed while HA was down reverts at startup."""
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat")
    until = dt_util.utcnow() - timedelta(minutes=5)
    mock_restore_cache(
        hass,
        [
            State(
                "climate.climate_orchestrator",
                "heat",
                {
                    "preset_mode": "boost",
                    "boost_until": until.isoformat(),
                    "boost_previous_preset": "sleep",
                    "boost_direction": "heat",
                },
            )
        ],
    )

    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get(entity_id_for("climate", config_entry.entry_id))
    assert state.attributes[ATTR_PRESET_MODE] == "sleep"
    assert "boost_until" not in state.attributes


async def test_boost_deselected_creates_no_entities(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Without boost in the selection there is no preset and no tunables."""
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat")
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_PRESETS: ["home", "away", "sleep"]}
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    cid = config_entry.entry_id
    climate = hass.states.get(entity_id_for("climate", cid))
    assert "boost" not in climate.attributes["preset_modes"]
    # entity_id_for asserts existence, so check the registry directly here.
    registry = er.async_get(hass)
    for key in ("boost_offset", "boost_duration"):
        assert registry.async_get_entity_id("number", DOMAIN, f"{cid}_{key}") is None


async def test_boost_events(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Boost fires started on selection and ended (cancelled) on takeover."""
    events = async_capture_events(hass, EVENT_CLIMATE_ORCHESTRATOR)
    climate_id = entity_id_for("climate", init_integration.entry_id)

    async def _preset(preset: str) -> None:
        await hass.services.async_call(
            "climate",
            "set_preset_mode",
            {ATTR_ENTITY_ID: climate_id, "preset_mode": preset},
            blocking=True,
        )
        await hass.async_block_till_done()

    await _preset("boost")
    started = _events_of(events, EVENT_TYPE_BOOST_STARTED)
    assert len(started) == 1
    assert started[0].data["direction"] == "heat"
    assert started[0].data["previous_preset"] == "home"
    assert started[0].data["until"]

    await _preset("sleep")
    ended = _events_of(events, EVENT_TYPE_BOOST_ENDED)
    assert len(ended) == 1
    assert ended[0].data["reason"] == "cancelled"
    assert ended[0].data["reverted_to"] == "sleep"
