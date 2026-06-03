"""Shared builders for arbitration-engine inputs.

Every engine-facing test builds the same two dataclasses with mostly-default
values; these factories keep the noise out of the tests. Defaults put the
reading mid-band (22.0 in a 20-24 band) so each test states only what it
cares about.
"""

from __future__ import annotations

from typing import Any

from custom_components.climate_orchestrator.control.engine import (
    DeviceInput,
    DeviceKind,
    GlobalInput,
)
from custom_components.climate_orchestrator.models import Band

BAND = Band(heat_edge=20.0, cool_edge=24.0)  # target = 22.0


def make_global(**overrides: Any) -> GlobalInput:
    """A GlobalInput mid-band, exact thresholds unless a test opts in."""
    base: dict[str, Any] = {
        "band": BAND,
        "release_offset": 0.5,
        "home_temp": 22.0,
        "use_comfort": False,
    }
    base.update(overrides)
    return GlobalInput(**base)


def make_heater(**overrides: Any) -> DeviceInput:
    """An available heater (TRV) reading mid-band."""
    base: dict[str, Any] = {
        "key": "trv",
        "kind": DeviceKind.HEATER,
        "available": True,
        "local_temp": 22.0,
    }
    base.update(overrides)
    return DeviceInput(**base)


def make_cooler(**overrides: Any) -> DeviceInput:
    """An available cooler (AC) reading mid-band."""
    base: dict[str, Any] = {
        "key": "ac",
        "kind": DeviceKind.COOLER,
        "available": True,
        "local_temp": 22.0,
    }
    base.update(overrides)
    return DeviceInput(**base)
