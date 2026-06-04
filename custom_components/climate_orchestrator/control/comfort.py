"""Comfort math: apparent temperature and dew point.

Pure functions with no Home Assistant dependencies. The "feels-like" target is
the Australian Bureau of Meteorology Apparent Temperature, evaluated indoors
(wind speed = 0). Unlike the US Heat Index it is a single continuous function
across the whole indoor range, so it works for both heating and cooling
(see docs/internals/control-model.md). The whole-home feels-like value is
also surfaced as a sensor so it's visible *why* the thermostat is (or isn't)
running.
"""

from __future__ import annotations

import math

# Magnus/Tetens coefficients over water (temperatures in °C).
_MAGNUS_A = 17.27
_MAGNUS_B = 237.7


def saturation_vapour_pressure(temp_c: float) -> float:
    """Saturation water-vapour pressure in hPa (Tetens formula)."""
    return 6.105 * math.exp(_MAGNUS_A * temp_c / (_MAGNUS_B + temp_c))


def vapour_pressure(temp_c: float, rh_pct: float) -> float:
    """Actual water-vapour pressure in hPa for a temperature and humidity."""
    return (rh_pct / 100.0) * saturation_vapour_pressure(temp_c)


def apparent_temperature(temp_c: float, rh_pct: float) -> float:
    """Australian BoM Apparent Temperature, indoors (wind term = 0)."""
    return temp_c + 0.33 * vapour_pressure(temp_c, rh_pct) - 4.00


def dew_point(temp_c: float, rh_pct: float) -> float:
    """Dew-point temperature in °C (Magnus approximation)."""
    rh = max(rh_pct, 1e-6)  # guard against log(0)
    gamma = (_MAGNUS_A * temp_c) / (_MAGNUS_B + temp_c) + math.log(rh / 100.0)
    return (_MAGNUS_B * gamma) / (_MAGNUS_A - gamma)


def effective_temperature(
    temp_c: float,
    rh_pct: float | None,
    *,
    use_comfort: bool = True,
    influence: float = 1.0,
) -> float:
    """Return the control temperature: a humidity-adjusted feels-like value.

    Blends dry-bulb toward the apparent temperature by ``influence``:

        effective = dry_bulb + influence * (apparent - dry_bulb)

    so ``influence = 0`` is pure dry-bulb (humidity ignored), ``1`` is the full
    BoM apparent temperature, and ``> 1`` amplifies the humidity effect. Falls
    back to dry-bulb when comfort targeting is disabled or humidity is missing.
    """
    if not use_comfort or rh_pct is None:
        return temp_c
    apparent = apparent_temperature(temp_c, rh_pct)
    return temp_c + influence * (apparent - temp_c)
