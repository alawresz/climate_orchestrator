"""Forecast preconditioning wiring: fetch + cache + per-step series."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.climate_orchestrator.const import (
    CONF_TRVS,
    CONF_WEATHER_ENTITY,
    DEFAULT_TITLE,
    DOMAIN,
)
from custom_components.climate_orchestrator.coordinator import SmartClimateCoordinator
from custom_components.climate_orchestrator.settings import resolve_settings
from tests.conftest import TRV_ENTITY

WEATHER = "weather.home"
_FORECAST = [5.0, 4.0, 3.0, 2.0, 1.0]


def _register_forecast_service(hass: HomeAssistant) -> None:
    async def _get_forecasts(call: ServiceCall) -> dict:
        return {
            WEATHER: {
                "forecast": [{"datetime": "x", "temperature": t} for t in _FORECAST]
            }
        }

    hass.services.async_register(
        "weather",
        "get_forecasts",
        _get_forecasts,
        supports_response=SupportsResponse.ONLY,
    )


async def test_forecast_is_fetched_cached_and_expanded(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Enabling the switch fetches the hourly forecast and builds a per-step series."""
    _register_forecast_service(hass)
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat", {"hvac_modes": ["off", "heat"]})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_TITLE,
        data={CONF_TRVS: [TRV_ENTITY], CONF_WEATHER_ENTITY: WEATHER},
        entry_id="sc_precond",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    cid = entry.entry_id
    coordinator: SmartClimateCoordinator = entry.runtime_data

    # Off by default -> no forecast pulled, no series.
    assert coordinator._forecast_hourly == []
    assert coordinator._precondition_series(1.0, resolve_settings(hass, cid)) is None

    await hass.services.async_call(
        "switch",
        "turn_on",
        {ATTR_ENTITY_ID: entity_id_for("switch", f"{cid}_forecast_preconditioning")},
        blocking=True,
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # The hourly forecast is cached, and the look-ahead expands onto 1-min steps.
    assert coordinator._forecast_hourly == _FORECAST
    series = coordinator._precondition_series(1.0, resolve_settings(hass, cid))
    assert series is not None
    assert len(series) == 120  # 2 h default look-ahead at a 1-min step
    assert series[0] == 5.0
