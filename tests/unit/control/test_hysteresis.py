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


# --- mutation-hardening: boundary/exact-value pins (mutmut survivors) ---


def test_heat_release_needs_both_at_target_exactly() -> None:
    """Release at local==home==target; either one short keeps heating."""
    kw = {"band": BAND, "release_offset": 0.5, "tolerance": 0.5}
    assert (
        evaluate_demand(local=20.5, home=20.5, previous=Demand.HEAT, **kw)
        is Demand.IDLE
    )
    assert (
        evaluate_demand(local=20.5, home=20.4, previous=Demand.HEAT, **kw)
        is Demand.HEAT
    )
    assert (
        evaluate_demand(local=20.4, home=20.5, previous=Demand.HEAT, **kw)
        is Demand.HEAT
    )


def test_heat_overshoot_releases_exactly_at_threshold() -> None:
    """Overshoot fires at exactly cool_edge - release_offset (home in-band)."""
    kw = {"band": BAND, "release_offset": 0.5, "tolerance": 0.5}
    assert (
        evaluate_demand(local=23.5, home=20.4, previous=Demand.HEAT, **kw)
        is Demand.IDLE
    )
    assert (
        evaluate_demand(local=23.4, home=20.4, previous=Demand.HEAT, **kw)
        is Demand.HEAT
    )


def test_cool_release_needs_both_at_target_exactly() -> None:
    kw = {"band": BAND, "release_offset": 0.5, "tolerance": 0.5}
    assert (
        evaluate_demand(local=23.5, home=23.5, previous=Demand.COOL, **kw)
        is Demand.IDLE
    )
    assert (
        evaluate_demand(local=23.5, home=23.6, previous=Demand.COOL, **kw)
        is Demand.COOL
    )
    assert (
        evaluate_demand(local=23.6, home=23.5, previous=Demand.COOL, **kw)
        is Demand.COOL
    )


def test_cool_overshoot_releases_exactly_at_threshold() -> None:
    """Overshoot fires at exactly heat_edge + release_offset (home in-band)."""
    kw = {"band": BAND, "release_offset": 0.5, "tolerance": 0.5}
    assert (
        evaluate_demand(local=20.5, home=23.7, previous=Demand.COOL, **kw)
        is Demand.IDLE
    )
    assert (
        evaluate_demand(local=20.6, home=23.7, previous=Demand.COOL, **kw)
        is Demand.COOL
    )


def test_engage_is_strictly_below_edge() -> None:
    """Sitting exactly ON the heat edge does not engage (strict <)."""
    kw = {"band": BAND, "release_offset": 0.5, "previous": Demand.IDLE}
    assert evaluate_demand(local=20.0, home=22.0, **kw) is Demand.IDLE
    assert evaluate_demand(local=22.0, home=20.0, **kw) is Demand.IDLE


def test_default_tolerance_is_zero() -> None:
    """Without tolerance the heat target IS the edge: 20/20 releases."""
    assert (
        evaluate_demand(
            local=20.0, home=20.0, band=BAND, release_offset=0.5, previous=Demand.HEAT
        )
        is Demand.IDLE
    )
