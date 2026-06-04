"""Per-area comfort band offset: an offset number per area biases that area."""

from __future__ import annotations

from collections.abc import Callable

from homeassistant.const import ATTR_ENTITY_ID
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from tests.conftest import AREA_TEMP_SENSOR
from tests.ha.helpers import refresh


async def test_area_offset_number_created_per_area(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    living_area: str,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """A managed area gets exactly one band-offset number, defaulting to 0."""
    cid = init_integration.entry_id
    offset = entity_id_for("number", f"{cid}_area_offset_{living_area}")
    state = hass.states.get(offset)
    assert state is not None
    assert float(state.state) == 0.0


async def test_positive_offset_makes_area_heat(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    living_area: str,
    entity_id_for: Callable[[str, str], str],
) -> None:
    """Raising an area's offset starts heating a room that was in band."""
    cid = init_integration.entry_id
    climate = entity_id_for("climate", cid)
    offset = entity_id_for("number", f"{cid}_area_offset_{living_area}")

    # Exact thresholds: drop the comfort transform so the band edges are literal.
    await hass.services.async_call(
        "switch",
        "turn_off",
        {ATTR_ENTITY_ID: entity_id_for("switch", f"{cid}_comfort_index_targeting")},
        blocking=True,
    )
    await hass.services.async_call(
        "climate",
        "set_hvac_mode",
        {ATTR_ENTITY_ID: climate, "hvac_mode": "heat_cool"},
        blocking=True,
    )

    # 21.0 sits inside the home band (heat edge 20.5) -> idle.
    hass.states.async_set(AREA_TEMP_SENSOR, "21.0", {"device_class": "temperature"})
    await refresh(hass, init_integration)
    assert hass.states.get(climate).attributes["hvac_action"] == "idle"

    # +3 offset pulls the perceived reading to 18.0 (< 20.5) -> heating.
    await hass.services.async_call(
        "number",
        "set_value",
        {ATTR_ENTITY_ID: offset, "value": 3.0},
        blocking=True,
    )
    await refresh(hass, init_integration)
    assert hass.states.get(climate).attributes["hvac_action"] == "heating"
