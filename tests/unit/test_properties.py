"""Property-based tests (Hypothesis) for the pure control core.

These assert invariants that must hold for *any* input — the kind of edge cases
hand-written examples miss: no NaNs, setpoints always within device limits, a
radiator never told to cool, the optimiser always in range, etc.
"""

from __future__ import annotations

import math

from hypothesis import given
from hypothesis import strategies as st

from custom_components.climate_orchestrator.control.adaptive_comfort import (
    adaptive_band,
)
from custom_components.climate_orchestrator.control.comfort import (
    apparent_temperature,
    dew_point,
    effective_temperature,
)
from custom_components.climate_orchestrator.control.engine import (
    DeviceDecision,
    DeviceInput,
    DeviceKind,
    GlobalInput,
    decide,
)
from custom_components.climate_orchestrator.control.hysteresis import Demand
from custom_components.climate_orchestrator.control.mpc.model import ThermalParams
from custom_components.climate_orchestrator.control.mpc.optimizer import optimize_valve
from custom_components.climate_orchestrator.control.slope import (
    temperature_slope_per_min,
)
from custom_components.climate_orchestrator.devices.command import build_command
from custom_components.climate_orchestrator.devices.model import AdapterCapabilities
from custom_components.climate_orchestrator.models import Band

_temps = st.floats(min_value=-20, max_value=50, allow_nan=False, allow_infinity=False)
_rh = st.floats(min_value=0, max_value=100, allow_nan=False, allow_infinity=False)


@st.composite
def _bands(draw: st.DrawFn) -> Band:
    low = draw(st.floats(min_value=5, max_value=30, allow_nan=False))
    width = draw(st.floats(min_value=0, max_value=20, allow_nan=False))
    return Band(heat_edge=low, cool_edge=low + width)


@st.composite
def _any_bands(draw: st.DrawFn) -> Band:
    """A band that may be sane, degenerate, or *inverted* (cool below heat)."""
    a = draw(st.floats(min_value=5, max_value=30, allow_nan=False))
    b = draw(st.floats(min_value=5, max_value=30, allow_nan=False))
    return Band(heat_edge=a, cool_edge=b)


@st.composite
def _caps(draw: st.DrawFn) -> AdapterCapabilities:
    lo = draw(st.floats(min_value=5, max_value=25, allow_nan=False))
    hi = draw(st.floats(min_value=lo + 1, max_value=40, allow_nan=False))
    step = draw(st.sampled_from([0.1, 0.5, 1.0]))
    return AdapterCapabilities(
        can_heat=True,
        can_cool=True,
        can_dry=True,
        min_temp=lo,
        max_temp=hi,
        target_step=step,
    )


@given(_temps, _rh)
def test_comfort_math_is_finite(temp: float, humidity: float) -> None:
    assert math.isfinite(apparent_temperature(temp, humidity))
    assert math.isfinite(dew_point(temp, humidity))
    assert math.isfinite(effective_temperature(temp, humidity))


@given(
    _bands(),
    st.one_of(st.none(), _temps),
    st.floats(0, 5, allow_nan=False),
    st.floats(-3, 3, allow_nan=False),
    st.floats(1, 10, allow_nan=False),
)
def test_adaptive_band_only_relaxes_cooling_within_max_shift(
    band: Band,
    outdoor: float | None,
    max_shift: float,
    bias: float,
    response: float,
) -> None:
    heat, cool = adaptive_band(
        band.heat_edge, band.cool_edge, outdoor, max_shift, bias=bias, response=response
    )
    # Heat edge is never touched; cool edge only ever rises, never past max_shift.
    assert heat == band.heat_edge
    assert cool >= band.cool_edge - 1e-9
    assert cool - band.cool_edge <= max_shift + 1e-9


@given(
    _bands(),
    _caps(),
    st.sampled_from([Demand.HEAT, Demand.COOL]),
    st.sampled_from([DeviceKind.HEATER, DeviceKind.COOLER]),
    st.floats(0, 10, allow_nan=False),
    st.floats(0, 3, allow_nan=False),
    st.one_of(st.none(), _temps),
    st.one_of(st.none(), _temps),
)
def test_setpoint_always_within_device_limits(
    band: Band,
    caps: AdapterCapabilities,
    demand: Demand,
    kind: DeviceKind,
    bias: float,
    tolerance: float,
    device_temp: float | None,
    room_temp: float | None,
) -> None:
    cmd = build_command(
        DeviceDecision(key="x", demand=demand, dry_mode=False, reason=""),
        kind,
        band=band,
        ac_setpoint_bias=bias,
        caps=caps,
        tolerance=tolerance,
        device_current_temp=device_temp,
        room_temp=room_temp,
    )
    if cmd.target_temp is not None:
        assert caps.min_temp - 1e-6 <= cmd.target_temp <= caps.max_temp + 1e-6


@given(_bands(), _temps, st.one_of(st.none(), _temps), st.booleans())
def test_heater_never_cools_and_ac_never_heats_without_assist(
    band: Band, local: float, home: float | None, comfort: bool
) -> None:
    glob = GlobalInput(
        band=band,
        release_offset=0.5,
        tolerance=0.3,
        home_temp=home,
        use_comfort=comfort,
    )
    heater = decide(
        DeviceInput(key="h", kind=DeviceKind.HEATER, available=True, local_temp=local),
        glob,
    )
    cooler = decide(
        DeviceInput(key="c", kind=DeviceKind.COOLER, available=True, local_temp=local),
        glob,
    )
    assert heater.demand is not Demand.COOL
    assert cooler.demand is not Demand.HEAT


@given(
    _any_bands(),
    _temps,
    st.one_of(st.none(), _temps),
    st.booleans(),
    st.booleans(),
    st.sampled_from(list(Demand)),
)
def test_heat_and_cool_never_engage_together(
    band: Band,
    local: float,
    home: float | None,
    comfort: bool,
    assist: bool,
    previous: Demand,
) -> None:
    """The core safety invariant: across a heater + AC, one is never heating
    while the other cools — for *any* band, including inverted/degenerate ones."""
    glob = GlobalInput(
        band=band,
        release_offset=0.5,
        tolerance=0.3,
        home_temp=home,
        use_comfort=comfort,
        ac_heating_assist=assist,
    )
    heater = decide(
        DeviceInput(
            key="h",
            kind=DeviceKind.HEATER,
            available=True,
            local_temp=local,
            previous=previous,
        ),
        glob,
    )
    cooler = decide(
        DeviceInput(
            key="c",
            kind=DeviceKind.COOLER,
            available=True,
            local_temp=local,
            previous=previous,
        ),
        glob,
    )
    demands = {heater.demand, cooler.demand}
    assert not (Demand.HEAT in demands and Demand.COOL in demands)


@given(
    _any_bands(),
    st.one_of(st.none(), _temps),
    st.one_of(st.none(), _temps),
    st.one_of(st.none(), _temps),
    st.one_of(st.none(), _rh),
    st.floats(0, 5, allow_nan=False),
    st.floats(0, 3, allow_nan=False),
    st.sampled_from(list(DeviceKind)),
    st.sampled_from(list(Demand)),
    st.booleans(),
    st.booleans(),
)
def test_decide_is_total_for_any_input(
    band: Band,
    local: float | None,
    home: float | None,
    outdoor: float | None,
    humidity: float | None,
    release: float,
    tol: float,
    kind: DeviceKind,
    previous: Demand,
    window: bool,
    comfort: bool,
) -> None:
    """`decide` never raises and always returns a valid Demand + reason, for
    arbitrary (incl. inverted) bands, missing temps/humidity, and every flag."""
    glob = GlobalInput(
        band=band,
        release_offset=release,
        tolerance=tol,
        home_temp=home,
        home_humidity=humidity,
        outdoor_temp=outdoor,
        use_comfort=comfort,
        dew_point_threshold=16.0,
        frost_temp=7.0,
        heat_off_outdoor=20.0,
        cool_off_outdoor=16.0,
    )
    decision = decide(
        DeviceInput(
            key="d",
            kind=kind,
            available=True,
            local_temp=local,
            local_humidity=humidity,
            window_open=window,
            previous=previous,
        ),
        glob,
    )
    assert decision.demand in set(Demand)
    assert isinstance(decision.reason, str) and decision.reason
    # Capability gating must always hold.
    if kind is DeviceKind.HEATER:
        assert decision.demand is not Demand.COOL


@given(st.lists(st.tuples(st.floats(0, 1e6, allow_nan=False), _temps), max_size=30))
def test_slope_is_none_or_finite(samples: list[tuple[float, float]]) -> None:
    result = temperature_slope_per_min(samples)
    assert result is None or math.isfinite(result)


@given(
    _temps,
    _temps,
    _temps,
    st.floats(0.01, 1.0, allow_nan=False),
    st.floats(0.0, 0.5, allow_nan=False),
)
def test_optimised_valve_stays_in_range(
    temp: float, target: float, outdoor: float, gain: float, loss: float
) -> None:
    valve = optimize_valve(
        temp, target, outdoor, ThermalParams(gain=gain, loss=loss), dt=1.0, horizon=6
    )
    assert 0.0 <= valve <= 1.0
