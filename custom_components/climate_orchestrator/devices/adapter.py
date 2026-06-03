"""Adapter that drives a Home Assistant ``climate`` entity.

Works for any climate entity (TRV or AC) since both expose the standard climate
services. Capabilities are detected from the entity's reported attributes, and
commands are applied via the minimal set of service calls (see reconcile).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.climate import (
    ATTR_HVAC_MODE,
    SERVICE_SET_HVAC_MODE,
    SERVICE_SET_TEMPERATURE,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import (
    ATTR_ENTITY_ID,
    ATTR_TEMPERATURE,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)

from ..const import MAX_TEMP, MIN_TEMP, TARGET_TEMP_STEP
from .model import AdapterCapabilities, DeviceCommand, DeviceState
from .reconcile import reconcile

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant


class ClimateAdapter:
    """Read and command a single Home Assistant climate entity."""

    def __init__(self, hass: HomeAssistant, entity_id: str) -> None:
        """Bind the adapter to an entity."""
        self.hass = hass
        self.entity_id = entity_id

    def read(self) -> DeviceState:
        """Snapshot the device's current state."""
        state = self.hass.states.get(self.entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return DeviceState(
                available=False, hvac_mode=None, current_temp=None, target_temp=None
            )
        return DeviceState(
            available=True,
            hvac_mode=state.state,
            current_temp=state.attributes.get("current_temperature"),
            target_temp=state.attributes.get("temperature"),
        )

    def capabilities(self) -> AdapterCapabilities:
        """Detect what the device supports from its reported attributes."""
        state = self.hass.states.get(self.entity_id)
        attrs = state.attributes if state is not None else {}
        modes = attrs.get("hvac_modes") or []
        return AdapterCapabilities(
            can_heat="heat" in modes,
            can_cool="cool" in modes,
            can_dry="dry" in modes,
            min_temp=attrs.get("min_temp", MIN_TEMP),
            max_temp=attrs.get("max_temp", MAX_TEMP),
            target_step=attrs.get("target_temp_step", TARGET_TEMP_STEP),
        )

    async def apply(self, command: DeviceCommand) -> None:
        """Issue the minimal service calls to reach ``command``."""
        state = self.read()
        if not state.available:
            return

        writes = reconcile(state, command, step=self.capabilities().target_step)
        if writes.set_hvac_mode is not None:
            await self.hass.services.async_call(
                CLIMATE_DOMAIN,
                SERVICE_SET_HVAC_MODE,
                {
                    ATTR_ENTITY_ID: self.entity_id,
                    ATTR_HVAC_MODE: writes.set_hvac_mode.value,
                },
                blocking=True,
            )
        if writes.set_temperature is not None:
            await self.hass.services.async_call(
                CLIMATE_DOMAIN,
                SERVICE_SET_TEMPERATURE,
                {
                    ATTR_ENTITY_ID: self.entity_id,
                    ATTR_TEMPERATURE: writes.set_temperature,
                },
                blocking=True,
            )
