"""Golden-trace regression for the pure control math, via syrupy snapshots.

These pin the *exact* numeric outputs of the comfort curves and the adaptive
cooling-comfort relaxation across a small grid, so an unintended change to the
math shows up as a snapshot diff in review rather than slipping through (line
coverage and Hypothesis invariants don't catch a subtly-shifted curve).

Snapshots live in ``tests/unit/snapshots/``. Regenerate them *intentionally*
(after confirming a diff is expected) with:

    uv run pytest tests/unit/test_snapshot_regression.py --snapshot-update

syrupy ships transitively with pytest-homeassistant-custom-component.
"""

from __future__ import annotations

from custom_components.climate_orchestrator.control.adaptive_comfort import (
    adaptive_band,
)
from custom_components.climate_orchestrator.control.comfort import (
    dew_point,
    effective_temperature,
)

_TEMPS = (18.0, 22.0, 26.0, 30.0)
_HUMIDITIES = (30.0, 50.0, 70.0)


def test_comfort_curve_snapshot(snapshot) -> None:
    """Pin the feels-like + dew-point grid across temperature/humidity."""
    grid = {
        f"{temp}C/{rh}%": {
            "effective": round(effective_temperature(temp, rh), 4),
            "dew_point": round(dew_point(temp, rh), 4),
        }
        for temp in _TEMPS
        for rh in _HUMIDITIES
    }
    assert grid == snapshot


def test_adaptive_cooling_comfort_snapshot(snapshot) -> None:
    """Pin the saturating cool-edge relaxation across the running-mean outdoor."""
    # Home preset 20.5/24.5, defaults: max_shift 2.0, onset bias +1.0, response 5.0.
    curve = {
        f"rmot={rmot}": [
            round(edge, 4)
            for edge in adaptive_band(20.5, 24.5, rmot, 2.0, bias=1.0, response=5.0)
        ]
        for rmot in (15.0, 22.0, 25.5, 28.0, 33.0, 45.0)
    }
    assert curve == snapshot
