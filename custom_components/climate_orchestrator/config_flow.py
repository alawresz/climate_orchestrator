"""Config and options flow for the Climate Orchestrator integration.

A single whole-home instance. The user selects the TRVs and ACs to orchestrate
plus an optional outdoor sensor and weather entity. Runtime tunables live on
entities, not here. Selections are editable later via the options flow.
"""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector
import voluptuous as vol

from .const import (
    CONF_ACS,
    CONF_CALIBRATION_HINTS,
    CONF_OUTDOOR_SENSOR,
    CONF_TRVS,
    CONF_VALVE_HINTS,
    CONF_WEATHER_ENTITY,
    DEFAULT_TITLE,
    DOMAIN,
)
from .coordinator import SmartClimateConfigEntry
from .devices.trv import LOCAL_CALIBRATION_HINTS, VALVE_OPENING_HINTS

_CLIMATE_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="climate", multiple=True)
)
_TEMP_SENSOR_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="sensor", device_class="temperature")
)
_WEATHER_SELECTOR = selector.EntitySelector(
    selector.EntitySelectorConfig(domain="weather")
)
_TEXT_SELECTOR = selector.TextSelector()

_DEFAULT_VALVE_HINTS = ", ".join(VALVE_OPENING_HINTS)
_DEFAULT_CALIBRATION_HINTS = ", ".join(LOCAL_CALIBRATION_HINTS)


def _optional(key: str, suggested: Any | None) -> vol.Optional:
    """An optional key, pre-filled with a suggested value when present."""
    if suggested in (None, ""):
        return vol.Optional(key)
    return vol.Optional(key, description={"suggested_value": suggested})


def _build_schema(defaults: dict[str, Any]) -> vol.Schema:
    """Build the device/sensor selection schema, pre-filled with defaults."""
    return vol.Schema(
        {
            vol.Optional(
                CONF_TRVS, default=list(defaults.get(CONF_TRVS, []))
            ): _CLIMATE_SELECTOR,
            vol.Optional(
                CONF_ACS, default=list(defaults.get(CONF_ACS, []))
            ): _CLIMATE_SELECTOR,
            _optional(
                CONF_OUTDOOR_SENSOR, defaults.get(CONF_OUTDOOR_SENSOR)
            ): _TEMP_SENSOR_SELECTOR,
            _optional(
                CONF_WEATHER_ENTITY, defaults.get(CONF_WEATHER_ENTITY)
            ): _WEATHER_SELECTOR,
            _optional(
                CONF_VALVE_HINTS,
                defaults.get(CONF_VALVE_HINTS, _DEFAULT_VALVE_HINTS),
            ): _TEXT_SELECTOR,
            _optional(
                CONF_CALIBRATION_HINTS,
                defaults.get(CONF_CALIBRATION_HINTS, _DEFAULT_CALIBRATION_HINTS),
            ): _TEXT_SELECTOR,
        }
    )


def _has_device(user_input: dict[str, Any]) -> bool:
    """At least one TRV or AC must be selected."""
    return bool(user_input.get(CONF_TRVS) or user_input.get(CONF_ACS))


class SmartClimateConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the Climate Orchestrator config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial setup step."""
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        errors: dict[str, str] = {}
        if user_input is not None:
            if not _has_device(user_input):
                errors["base"] = "no_devices"
            else:
                return self.async_create_entry(title=DEFAULT_TITLE, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_build_schema(user_input or {}),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: SmartClimateConfigEntry,
    ) -> SmartClimateOptionsFlow:
        """Return the options flow handler."""
        return SmartClimateOptionsFlow()


class SmartClimateOptionsFlow(OptionsFlow):
    """Edit the selected devices and sources after setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if not _has_device(user_input):
                errors["base"] = "no_devices"
            else:
                return self.async_create_entry(title="", data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_build_schema(user_input or current),
            errors=errors,
        )
