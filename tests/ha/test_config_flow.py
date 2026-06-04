"""Tests for the Climate Orchestrator config and options flows."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_orchestrator.const import (
    CONF_ACS,
    CONF_CALIBRATION_HINTS,
    CONF_PRESETS,
    CONF_TRVS,
    CONF_VALVE_HINTS,
    DEFAULT_TITLE,
    DOMAIN,
    SELECTABLE_PRESETS,
)
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from custom_components.climate_orchestrator.devices.trv import VALVE_OPENING_HINTS
from tests.conftest import AC_ENTITY, TRV_ENTITY


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """The user flow shows a form and then creates the entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_TRVS: [TRV_ENTITY], CONF_ACS: [AC_ENTITY]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == DEFAULT_TITLE
    assert result["data"][CONF_TRVS] == [TRV_ENTITY]
    assert result["data"][CONF_ACS] == [AC_ENTITY]


async def test_user_flow_requires_a_device(hass: HomeAssistant) -> None:
    """Submitting with no devices selected re-shows the form with an error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_devices"}


async def test_single_instance_only(hass: HomeAssistant) -> None:
    """A second config flow aborts because only one instance is allowed."""
    MockConfigEntry(domain=DOMAIN, data={CONF_TRVS: [TRV_ENTITY]}).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_options_flow_edits_devices(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The options flow updates the selected devices."""
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TRVS: [TRV_ENTITY], CONF_ACS: []}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert init_integration.options[CONF_TRVS] == [TRV_ENTITY]
    assert init_integration.options[CONF_ACS] == []


async def test_discovery_hints_default_when_unset(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """With no override, the coordinator uses the built-in Zigbee2MQTT hints."""
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    assert coordinator.valve_hints == VALVE_OPENING_HINTS


async def test_options_flow_sets_custom_discovery_hints(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """Custom comma-separated hints flow through to the coordinator."""
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_TRVS: [TRV_ENTITY],
            CONF_ACS: [AC_ENTITY],
            CONF_VALVE_HINTS: "My Valve, custom_pos",
            CONF_CALIBRATION_HINTS: "my_calib",
        },
    )
    await hass.async_block_till_done()

    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    # Parsed, trimmed, lower-cased into a tuple.
    assert coordinator.valve_hints == ("my valve", "custom_pos")
    assert coordinator.calibration_hints == ("my_calib",)


async def test_options_flow_stores_preset_selection(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The preset multi-select round-trips into options and the coordinator."""
    coordinator: SmartClimateCoordinator = init_integration.runtime_data
    assert coordinator.enabled_presets == list(SELECTABLE_PRESETS)  # default: all

    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_TRVS: [TRV_ENTITY], CONF_ACS: [AC_ENTITY], CONF_PRESETS: ["home"]},
    )
    await hass.async_block_till_done()

    assert init_integration.options[CONF_PRESETS] == ["home"]
    coordinator = init_integration.runtime_data  # reloaded entry
    assert coordinator.enabled_presets == ["home"]


async def test_options_flow_requires_a_device(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    """The options flow rejects clearing all devices."""
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_TRVS: [], CONF_ACS: []}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "no_devices"}
