"""Forecast preconditioning wiring: fetch + cache + per-step series."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import issue_registry as ir
import pytest
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
from tests.ha.helpers import (
    age_forecast_failure,
    expire_forecast,
    forecast_cache,
    precondition_series,
)

WEATHER = "weather.home"
_FORECAST = [5.0, 4.0, 3.0, 2.0, 1.0]


def _register_forecast_service(
    hass: HomeAssistant, temps: list[float] | None = None
) -> None:
    series = _FORECAST if temps is None else temps

    async def _get_forecasts(_call: ServiceCall) -> dict:
        return {
            WEATHER: {"forecast": [{"datetime": "x", "temperature": t} for t in series]}
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
    assert forecast_cache(coordinator) == []
    assert precondition_series(coordinator, 1.0, resolve_settings(hass, cid)) is None

    await hass.services.async_call(
        "switch",
        "turn_on",
        {ATTR_ENTITY_ID: entity_id_for("switch", f"{cid}_forecast_preconditioning")},
        blocking=True,
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    # The hourly forecast is cached, and the look-ahead expands onto 1-min steps.
    assert forecast_cache(coordinator) == _FORECAST
    series = precondition_series(coordinator, 1.0, resolve_settings(hass, cid))
    assert series is not None
    assert len(series) == 120  # 2 h default look-ahead at a 1-min step
    assert series[0] == 5.0


async def test_stale_forecast_is_ignored_not_trusted(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A forecast from a long-dead weather entity stops feeding the optimiser.

    Refreshes retry every cycle, so an hours-old cache means the weather
    entity is persistently failing — preconditioning must fall back to
    no-forecast behaviour rather than steer the valve on dead data.
    """
    _register_forecast_service(hass)
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat", {"hvac_modes": ["off", "heat"]})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_TITLE,
        data={CONF_TRVS: [TRV_ENTITY], CONF_WEATHER_ENTITY: WEATHER},
        entry_id="sc_precond_stale",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    cid = entry.entry_id
    coordinator: SmartClimateCoordinator = entry.runtime_data
    await hass.services.async_call(
        "switch",
        "turn_on",
        {ATTR_ENTITY_ID: entity_id_for("switch", f"{cid}_forecast_preconditioning")},
        blocking=True,
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert precondition_series(coordinator, 1.0, resolve_settings(hass, cid))

    expire_forecast(coordinator)
    assert precondition_series(coordinator, 1.0, resolve_settings(hass, cid)) is None


async def test_hourly_forecast_cache_is_capped(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A weather entity returning a huge forecast can't grow the cache."""
    _register_forecast_service(hass, temps=[float(i) for i in range(200)])
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat", {"hvac_modes": ["off", "heat"]})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_TITLE,
        data={CONF_TRVS: [TRV_ENTITY], CONF_WEATHER_ENTITY: WEATHER},
        entry_id="sc_precond_cap",
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    cid = entry.entry_id
    coordinator: SmartClimateCoordinator = entry.runtime_data
    await hass.services.async_call(
        "switch",
        "turn_on",
        {ATTR_ENTITY_ID: entity_id_for("switch", f"{cid}_forecast_preconditioning")},
        blocking=True,
    )
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert len(forecast_cache(coordinator)) == 48  # _FORECAST_MAX_HOURS
    assert forecast_cache(coordinator)[0] == 0.0


async def _setup_preconditioning_entry(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
    entry_id: str,
) -> MockConfigEntry:
    """Set up a TRV + weather entry with the preconditioning switch on."""
    register_entity_in_area(TRV_ENTITY, living_area)
    hass.states.async_set(TRV_ENTITY, "heat", {"hvac_modes": ["off", "heat"]})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title=DEFAULT_TITLE,
        data={CONF_TRVS: [TRV_ENTITY], CONF_WEATHER_ENTITY: WEATHER},
        entry_id=entry_id,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    await hass.services.async_call(
        "switch",
        "turn_on",
        {
            ATTR_ENTITY_ID: entity_id_for(
                "switch", f"{entry.entry_id}_forecast_preconditioning"
            )
        },
        blocking=True,
    )
    return entry


@pytest.mark.parametrize(
    "response",
    [
        None,
        {"weather.elsewhere": {"forecast": [{"temperature": 5.0}]}},
        {WEATHER: "warm with a chance of rain"},
        {WEATHER: {"forecast": "sunny"}},
        {
            WEATHER: {
                "forecast": [
                    42,
                    {"temperature": "hot"},
                    {"temperature": True},
                    {"temperature": float("inf")},
                    {"datetime": "x"},
                ]
            }
        },
    ],
)
async def test_malformed_forecast_response_is_ignored(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
    response: dict[str, Any] | None,
) -> None:
    """Whatever shape a broken weather entity returns, the cache stays empty.

    The service response is loosely typed JSON; every narrowing step must
    hold — a junk payload no-ops the feature instead of poisoning the
    optimiser (or raising mid-cycle).
    """

    async def _get_forecasts(_call: ServiceCall) -> dict[str, Any] | None:
        return response

    hass.services.async_register(
        "weather",
        "get_forecasts",
        _get_forecasts,
        supports_response=SupportsResponse.ONLY,
    )
    entry = await _setup_preconditioning_entry(
        hass, living_area, register_entity_in_area, entity_id_for, "sc_precond_bad"
    )

    coordinator: SmartClimateCoordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert forecast_cache(coordinator) == []
    settings = resolve_settings(hass, entry.entry_id)
    assert precondition_series(coordinator, 1.0, settings) is None


async def test_forecast_fetch_failure_is_swallowed(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A raising weather service must not break the control cycle."""

    outage = HomeAssistantError("weather provider outage")

    async def _get_forecasts(_call: ServiceCall) -> dict[str, Any]:
        raise outage

    hass.services.async_register(
        "weather",
        "get_forecasts",
        _get_forecasts,
        supports_response=SupportsResponse.ONLY,
    )
    entry = await _setup_preconditioning_entry(
        hass, living_area, register_entity_in_area, entity_id_for, "sc_precond_err"
    )

    coordinator: SmartClimateCoordinator = entry.runtime_data
    await coordinator.async_refresh()
    await hass.async_block_till_done()

    assert forecast_cache(coordinator) == []
    settings = resolve_settings(hass, entry.entry_id)
    assert precondition_series(coordinator, 1.0, settings) is None
    # The cycle survived: the coordinator still produced a snapshot.
    assert coordinator.last_update_success


async def test_persistent_forecast_failure_raises_and_clears(
    hass: HomeAssistant,
    living_area: str,
    register_entity_in_area: Callable[[str, str | None], str],
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A weather entity whose forecast keeps failing surfaces a repair.

    A single failure is debounced; only a sustained one raises, and a
    recovered fetch clears it.
    """
    outage = HomeAssistantError("weather provider outage")

    async def _failing(_call: ServiceCall) -> dict[str, Any]:
        raise outage

    hass.services.async_register(
        "weather", "get_forecasts", _failing, supports_response=SupportsResponse.ONLY
    )
    entry = await _setup_preconditioning_entry(
        hass, living_area, register_entity_in_area, entity_id_for, "sc_precond_repair"
    )
    coordinator: SmartClimateCoordinator = entry.runtime_data
    registry = ir.async_get(hass)
    issue = "weather_forecast_unavailable"

    # Failing, but the streak only just started -> debounced, no repair.
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert registry.async_get_issue(DOMAIN, issue) is None

    # Sustained past the threshold -> the next cycle raises the repair.
    age_forecast_failure(coordinator)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert registry.async_get_issue(DOMAIN, issue) is not None

    # The weather entity recovers -> a successful fetch clears the notice.
    _register_forecast_service(hass)
    await coordinator.async_refresh()
    await hass.async_block_till_done()
    assert registry.async_get_issue(DOMAIN, issue) is None
    assert forecast_cache(coordinator) == _FORECAST
