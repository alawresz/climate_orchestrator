"""Regression (golden-trace) tests.

These pin the *exact* behaviour of the deterministic decision logic so future
refactors can't silently change it. If one fails, the behaviour changed — decide
whether that was intended before updating the golden values.
"""

from __future__ import annotations

import pytest

from custom_components.climate_orchestrator.control.comfort import (
    apparent_temperature,
    dew_point,
)
from custom_components.climate_orchestrator.control.engine import (
    DeviceInput,
    DeviceKind,
    GlobalInput,
    decide,
)
from custom_components.climate_orchestrator.control.hysteresis import (
    Demand,
    evaluate_demand,
)
from custom_components.climate_orchestrator.control.mpc.model import ThermalParams
from custom_components.climate_orchestrator.control.mpc.optimizer import optimize_valve
from custom_components.climate_orchestrator.models import Band

BAND = Band(heat_edge=20.0, cool_edge=24.0)  # target 22.0


def test_hysteresis_golden_timeline() -> None:
    """A scripted cold→warm→hot swing yields a fixed demand sequence."""
    readings = [
        (19.0, 19.0),
        (20.0, 20.0),
        (21.5, 21.5),
        (22.0, 22.0),
        (25.0, 25.0),
        (23.0, 23.0),
        (22.0, 22.0),
    ]
    # Targets at tolerance 0.3: heat_target 20.3, cool_target 23.7.
    expected = [
        Demand.HEAT,
        Demand.HEAT,
        Demand.IDLE,
        Demand.IDLE,
        Demand.COOL,
        Demand.IDLE,
        Demand.IDLE,
    ]
    previous = Demand.IDLE
    result = []
    for local, home in readings:
        previous = evaluate_demand(
            local=local,
            home=home,
            band=BAND,
            release_offset=0.5,
            previous=previous,
            tolerance=0.3,
        )
        result.append(previous)
    assert result == expected


def test_hysteresis_home_only_engage() -> None:
    """The home average alone (local fine) still engages heating."""
    assert (
        evaluate_demand(
            local=22.0, home=19.0, band=BAND, release_offset=0.5, previous=Demand.IDLE
        )
        is Demand.HEAT
    )


def test_engine_golden_heater_timeline() -> None:
    """A heater driven through a warming room yields a fixed sequence."""
    temps = [18.0, 20.0, 22.0, 25.0]
    expected = [Demand.HEAT, Demand.HEAT, Demand.IDLE, Demand.IDLE]
    previous = Demand.IDLE
    result = []
    for temp in temps:
        decision = decide(
            DeviceInput(
                key="trv",
                kind=DeviceKind.HEATER,
                available=True,
                local_temp=temp,
                previous=previous,
            ),
            GlobalInput(
                band=BAND,
                release_offset=0.5,
                tolerance=0.3,
                home_temp=temp,
                use_comfort=False,
            ),
        )
        previous = decision.demand
        result.append(decision.demand)
    assert result == expected


def test_comfort_values_pinned() -> None:
    """Lock the comfort formulas to known reference outputs."""
    assert apparent_temperature(25.0, 50) == pytest.approx(26.21, abs=0.02)
    assert dew_point(25.0, 50) == pytest.approx(13.84, abs=0.02)


def test_optimizer_value_pinned() -> None:
    """Lock the MPC optimiser to a known interior optimum."""
    params = ThermalParams(gain=0.25, loss=0.02)
    valve = optimize_valve(20.8, 21.0, 15.0, params, dt=1.0, horizon=6)
    assert valve == pytest.approx(0.657, abs=0.02)
