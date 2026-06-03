"""Tests for the asymmetric hysteresis demand logic."""

from __future__ import annotations

from custom_components.climate_orchestrator.control.hysteresis import (
    Demand,
    evaluate_demand,
)
from custom_components.climate_orchestrator.models import Band

BAND = Band(heat_edge=20.0, cool_edge=24.0)  # target = 22.0


def _demand(
    local: float,
    home: float,
    previous: Demand = Demand.IDLE,
    release_offset: float = 0.5,
    tolerance: float = 0.0,
) -> Demand:
    return evaluate_demand(
        local=local,
        home=home,
        band=BAND,
        release_offset=release_offset,
        previous=previous,
        tolerance=tolerance,
    )


def test_idle_in_neutral_zone() -> None:
    """Inside the band, do nothing."""
    assert _demand(22.0, 22.0) is Demand.IDLE


def test_engage_heat_on_local_or_home() -> None:
    """Either the local OR the home reading below the edge engages heating."""
    assert _demand(19.0, 22.0) is Demand.HEAT  # local triggers
    assert _demand(22.0, 19.0) is Demand.HEAT  # home triggers


def test_engage_cool_on_local_or_home() -> None:
    """Either reading above the edge engages cooling."""
    assert _demand(25.0, 22.0) is Demand.COOL
    assert _demand(22.0, 25.0) is Demand.COOL


def test_heating_drives_to_edge_plus_tolerance() -> None:
    """Heating runs until BOTH readings reach heat_edge + tolerance (20.5)."""
    # Below the target: keep heating.
    assert _demand(20.3, 20.0, previous=Demand.HEAT, tolerance=0.5) is Demand.HEAT
    # Both at/above the target: stop (settles just above the heat edge).
    assert _demand(20.6, 20.6, previous=Demand.HEAT, tolerance=0.5) is Demand.IDLE


def test_cooling_drives_to_edge_minus_tolerance() -> None:
    """Cooling runs until BOTH readings reach cool_edge - tolerance (23.5)."""
    assert _demand(23.7, 24.0, previous=Demand.COOL, tolerance=0.5) is Demand.COOL
    assert _demand(23.4, 23.4, previous=Demand.COOL, tolerance=0.5) is Demand.IDLE


def test_engage_at_the_edge_regardless_of_tolerance() -> None:
    """Engagement is at the trigger edge; tolerance only moves the target."""
    assert _demand(19.9, 22.0, tolerance=0.5) is Demand.HEAT  # < heat edge 20
    assert _demand(24.1, 22.0, tolerance=0.5) is Demand.COOL  # > cool edge 24


def test_tolerance_gap_prevents_short_cycling() -> None:
    """Engage at the edge, release past it: a small wiggle can't re-trigger."""
    # Settled idle just above the heat edge (between 20.0 and 20.5): stays idle.
    assert _demand(20.2, 20.2, previous=Demand.IDLE, tolerance=0.5) is Demand.IDLE


def test_heating_early_out_on_overshoot() -> None:
    """Heating stops early if the room nears the cooling edge."""
    # cool_edge - release_offset = 23.5
    assert _demand(23.6, 21.0, previous=Demand.HEAT) is Demand.IDLE


def test_cooling_early_out_on_undershoot() -> None:
    """Cooling stops early if the room nears the heating edge."""
    # heat_edge + release_offset = 20.5
    assert _demand(20.4, 23.0, previous=Demand.COOL) is Demand.IDLE
