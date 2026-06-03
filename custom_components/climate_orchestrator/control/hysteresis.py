"""Asymmetric hysteresis: decide heating/cooling demand for one device.

Engage on *local OR home-average* crossing a band edge; release only when
*both* are back at the target, or an early-out when the room nears the opposite
edge. This OR-to-engage / AND-to-release asymmetry suppresses short-cycling
(see DESIGN.md §5.2). Pure functions — no Home Assistant dependencies.
"""

from __future__ import annotations

from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..models import Band


class Demand(StrEnum):
    """What a device is being asked to do this cycle."""

    HEAT = "heat"
    COOL = "cool"
    IDLE = "idle"


def _heat_releases(
    local: float, home: float, band: Band, tolerance: float, release_offset: float
) -> bool:
    """Heating stops when both reach the heat target, or the room ran hot."""
    target = band.heat_target(tolerance)
    back_to_target = local >= target and home >= target
    overshoot = local >= band.cool_edge - release_offset
    return back_to_target or overshoot


def _cool_releases(
    local: float, home: float, band: Band, tolerance: float, release_offset: float
) -> bool:
    """Cooling stops when both reach the cool target, or the room ran cold."""
    target = band.cool_target(tolerance)
    back_to_target = local <= target and home <= target
    overshoot = local <= band.heat_edge + release_offset
    return back_to_target or overshoot


def evaluate_demand(
    *,
    local: float,
    home: float,
    band: Band,
    release_offset: float,
    previous: Demand,
    tolerance: float = 0.0,
) -> Demand:
    """Return the demand for a device given local and home-average readings.

    A device engages when *either* reading crosses the trigger edge (eager
    OR-trigger). It then drives to ``edge ± tolerance`` (the control target,
    capped at the midpoint) and releases only when *both* readings reach it — so
    rooms settle just past the comfort edge rather than at the band middle. The
    ``tolerance`` gap (engage at the edge, release past it) is what prevents
    short-cycling on jitter.
    """
    # Stay engaged until the release condition is met (conservative).
    if previous is Demand.HEAT and not _heat_releases(
        local, home, band, tolerance, release_offset
    ):
        return Demand.HEAT
    if previous is Demand.COOL and not _cool_releases(
        local, home, band, tolerance, release_offset
    ):
        return Demand.COOL

    # Fresh engagement: either signal crossing an edge is enough (eager).
    if local < band.heat_edge or home < band.heat_edge:
        return Demand.HEAT
    if local > band.cool_edge or home > band.cool_edge:
        return Demand.COOL
    return Demand.IDLE
