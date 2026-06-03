"""Tests for the arbitration engine."""

from __future__ import annotations

from typing import Any

from custom_components.climate_orchestrator.control.comfort import dew_point
from custom_components.climate_orchestrator.control.engine import (
    DeviceInput,
    DeviceKind,
    GlobalInput,
    decide,
)
from custom_components.climate_orchestrator.control.hysteresis import Demand
from custom_components.climate_orchestrator.models import Band

BAND = Band(heat_edge=20.0, cool_edge=24.0)  # target = 22.0


def _global(**overrides: Any) -> GlobalInput:
    base: dict[str, Any] = {
        "band": BAND,
        "release_offset": 0.5,
        "home_temp": 22.0,
        "use_comfort": False,  # exact thresholds unless a test opts in
    }
    base.update(overrides)
    return GlobalInput(**base)


def _heater(**overrides: Any) -> DeviceInput:
    base: dict[str, Any] = {
        "key": "trv",
        "kind": DeviceKind.HEATER,
        "available": True,
        "local_temp": 22.0,
    }
    base.update(overrides)
    return DeviceInput(**base)


def _cooler(**overrides: Any) -> DeviceInput:
    base: dict[str, Any] = {
        "key": "ac",
        "kind": DeviceKind.COOLER,
        "available": True,
        "local_temp": 22.0,
    }
    base.update(overrides)
    return DeviceInput(**base)


def test_worked_example_or_engage_and_release() -> None:
    """AC engages on local OR home over the edge; stays until both return."""
    assert decide(_cooler(local_temp=24.5), _global()).demand is Demand.COOL
    assert decide(_cooler(), _global(home_temp=24.5)).demand is Demand.COOL

    # Cool target = cool_edge - tolerance = 24 - 0.5 = 23.5; release needs BOTH
    # readings at/under it (local defaults to 22, already under).
    cooling = _cooler(previous=Demand.COOL)
    assert decide(cooling, _global(home_temp=23.8, tolerance=0.5)).demand is Demand.COOL
    assert decide(cooling, _global(home_temp=23.0, tolerance=0.5)).demand is Demand.IDLE


def test_heater_cannot_cool() -> None:
    """A radiator never cools, even when the room is hot."""
    assert decide(_heater(local_temp=26.0), _global()).demand is Demand.IDLE


def test_cooler_heats_only_with_assist() -> None:
    """An AC heats only when the heating-assist flag is enabled."""
    cold = _cooler(local_temp=18.0)
    assert decide(cold, _global()).demand is Demand.IDLE
    assert decide(cold, _global(ac_heating_assist=True)).demand is Demand.HEAT


def test_positive_area_offset_runs_room_warmer() -> None:
    """A positive offset makes the area heat sooner and cool later."""
    # Local 20.5 sits just inside the band -> idle without an offset.
    assert decide(_heater(local_temp=20.5), _global()).demand is Demand.IDLE
    # +1 offset drops the perceived reading to 19.5 (< heat_edge 20) -> heat.
    assert decide(_heater(local_temp=20.5, offset=1.0), _global()).demand is Demand.HEAT

    # Local 24.5 is over the cool edge -> the AC would cool...
    assert decide(_cooler(local_temp=24.5), _global()).demand is Demand.COOL
    # ...but a +1 offset (warmer) pulls it to 23.5, back inside the band -> idle.
    assert decide(_cooler(local_temp=24.5, offset=1.0), _global()).demand is Demand.IDLE


def test_area_offset_does_not_touch_home_branch() -> None:
    """The offset biases only the local reading; the home fallback is untouched."""
    # No local reading -> the engine falls back to the home average (22, in band).
    # Even a large offset must not synthesize a demand from the home branch.
    no_local = _heater(local_temp=None, offset=5.0)
    assert decide(no_local, _global()).demand is Demand.IDLE


def test_frost_protection_overrides_everything() -> None:
    """Below the frost temperature, a heater heats even with a window open."""
    decision = decide(
        _heater(local_temp=5.0, window_open=True),
        _global(frost_protection=True, frost_temp=7.0),
    )
    assert decision.demand is Demand.HEAT
    assert decision.reason == "frost_protection"


def test_window_open_suppresses_demand() -> None:
    """An open window in the area idles the device."""
    decision = decide(_heater(local_temp=18.0, window_open=True), _global())
    assert decision.demand is Demand.IDLE
    assert decision.reason == "window_open"


def test_ac_ignore_window_lets_cooler_run_on_its_own_window() -> None:
    """A portable split ignores *its own* room's (vent) window when exempted."""
    # Own window open, nothing open elsewhere.
    hot = _cooler(local_temp=26.0, window_open=True, other_window_open=False)
    # Default: its own open window still idles the AC.
    assert decide(hot, _global()).demand is Demand.IDLE
    # With the exemption on, the AC cools despite its own open window.
    assert decide(hot, _global(ac_ignore_window=True)).demand is Demand.COOL


def test_ac_ignore_window_still_suppressed_by_another_room() -> None:
    """The exemption only covers the AC's own room; another room's window stops it."""
    hot = _cooler(local_temp=26.0, window_open=True, other_window_open=True)
    decision = decide(hot, _global(ac_ignore_window=True))
    assert decision.demand is Demand.IDLE
    assert decision.reason == "window_open"


def test_ac_ignore_window_does_not_affect_heaters() -> None:
    """The exemption is cooler-only; a heater still stops with a window open."""
    decision = decide(
        _heater(local_temp=18.0, window_open=True),
        _global(ac_ignore_window=True),
    )
    assert decision.demand is Demand.IDLE
    assert decision.reason == "window_open"


def test_outdoor_gating_suppresses_heating() -> None:
    """Warm outside suppresses heating demand."""
    decision = decide(
        _heater(local_temp=18.0),
        _global(outdoor_gating=True, heat_off_outdoor=18.0, outdoor_temp=20.0),
    )
    assert decision.demand is Demand.IDLE
    assert decision.reason == "outdoor_gating"


def test_master_off_and_unavailable_idle() -> None:
    """Master-off and unavailable devices are idled with a clear reason."""
    assert decide(_heater(local_temp=18.0), _global(master_off=True)).reason == (
        "master_off"
    )
    assert decide(_heater(available=False, local_temp=18.0), _global()).reason == (
        "unavailable"
    )


def test_dew_point_guard_runs_ac_dry_when_idle() -> None:
    """An idle AC in a muggy room switches to dry mode."""
    decision = decide(
        _cooler(local_temp=22.0, local_humidity=90),
        _global(dew_point_threshold=16.0),
    )
    assert decision.demand is Demand.IDLE
    assert decision.dry_mode is True
    assert decision.reason == "dew_point_guard"


def test_comfort_index_engages_cooling_earlier() -> None:
    """With comfort on, a humid room cools at a dry-bulb temp that wouldn't."""
    cooler = _cooler(local_temp=24.0, local_humidity=80)
    dry = _global(home_temp=24.0)
    humid = _global(home_temp=24.0, home_humidity=80, use_comfort=True)
    assert decide(cooler, dry).demand is Demand.IDLE
    assert decide(cooler, humid).demand is Demand.COOL


def test_outdoor_gating_suppresses_cooling() -> None:
    """Cool enough outside suppresses cooling demand."""
    decision = decide(
        _cooler(local_temp=26.0),
        _global(outdoor_gating=True, cool_off_outdoor=14.0, outdoor_temp=12.0),
    )
    assert decision.demand is Demand.IDLE


def test_dew_point_guard_not_applied_while_cooling() -> None:
    """An actively cooling AC already dehumidifies, so no extra dry mode."""
    decision = decide(
        _cooler(local_temp=26.0, local_humidity=90),
        _global(dew_point_threshold=16.0),
    )
    assert decision.demand is Demand.COOL
    assert decision.dry_mode is False


def test_frost_protection_does_not_force_a_cooler() -> None:
    """Frost protection only applies to heaters, never an AC."""
    decision = decide(
        _cooler(local_temp=5.0),
        _global(frost_protection=True, frost_temp=7.0),
    )
    assert decision.demand is not Demand.HEAT
    assert decision.reason != "frost_protection"


def test_window_open_ignored_when_detection_disabled() -> None:
    """With window detection off, an open window no longer suppresses demand."""
    decision = decide(
        _heater(local_temp=18.0, window_open=True),
        _global(window_detection=False),
    )
    assert decision.demand is Demand.HEAT


# --- mutation-hardening: boundary/exact-value pins (mutmut survivors) ---


def test_frost_triggers_strictly_below_threshold() -> None:
    """At exactly the frost temperature the reason is plain heating, not frost."""
    decision = decide(_heater(local_temp=7.0), _global(frost_temp=7.0))
    assert decision.demand is Demand.HEAT
    assert decision.reason == "heat"
    assert decision.key == "trv"
    assert decision.dry_mode is False


def test_comfort_humidity_drives_local_decision() -> None:
    """A humid room at the cool edge feels hotter and engages cooling."""
    device = _cooler(local_temp=24.0, local_humidity=90.0)
    assert decide(device, _global(use_comfort=True)).demand is Demand.COOL


def test_comfort_influence_zero_neutralises_local_humidity() -> None:
    device = _cooler(local_temp=24.0, local_humidity=90.0)
    g = _global(use_comfort=True, comfort_influence=0.0)
    assert decide(device, g).demand is Demand.IDLE


def test_comfort_humidity_drives_home_fallback_decision() -> None:
    g = _global(use_comfort=True, home_temp=24.0, home_humidity=90.0)
    assert decide(_cooler(local_temp=None), g).demand is Demand.COOL


def test_comfort_influence_zero_neutralises_home_humidity() -> None:
    g = _global(
        use_comfort=True, home_temp=24.0, home_humidity=90.0, comfort_influence=0.0
    )
    assert decide(_cooler(local_temp=None), g).demand is Demand.IDLE


def test_no_data_decision_fields() -> None:
    decision = decide(_heater(local_temp=None), _global(home_temp=None))
    assert decision.demand is Demand.IDLE
    assert decision.reason == "no_data"
    assert decision.key == "trv"
    assert decision.dry_mode is False


def test_hot_day_cooling_is_not_outdoor_gated() -> None:
    """Heat gating must never suppress a cooling call on a hot day."""
    g = _global(outdoor_temp=25.0, heat_off_outdoor=20.0, cool_off_outdoor=16.0)
    decision = decide(_cooler(local_temp=26.0), g)
    assert decision.demand is Demand.COOL
    assert decision.reason == "cool"


def test_heat_gating_engages_exactly_at_cutoff() -> None:
    g = _global(outdoor_temp=20.0, heat_off_outdoor=20.0)
    decision = decide(_heater(local_temp=18.0), g)
    assert decision.demand is Demand.IDLE
    assert decision.reason == "outdoor_gating"


def test_cool_gating_engages_exactly_at_cutoff() -> None:
    g = _global(outdoor_temp=16.0, cool_off_outdoor=16.0)
    decision = decide(_cooler(local_temp=26.0), g)
    assert decision.demand is Demand.IDLE
    assert decision.reason == "outdoor_gating"


def test_dew_point_guard_is_strictly_above_threshold() -> None:
    """Dew point exactly equal to the threshold does NOT trigger dry mode."""
    threshold = dew_point(22.0, 60.0)
    device = _cooler(local_temp=22.0, local_humidity=60.0)
    assert decide(device, _global(dew_point_threshold=threshold)).dry_mode is False

    decision = decide(device, _global(dew_point_threshold=threshold - 1.0))
    assert decision.dry_mode is True
    assert decision.key == "ac"


def test_master_off_decision_fields() -> None:
    decision = decide(_heater(local_temp=18.0), _global(master_off=True))
    assert decision.demand is Demand.IDLE
    assert decision.reason == "master_off"


def test_unavailable_decision_fields() -> None:
    decision = decide(_heater(local_temp=18.0, available=False), _global())
    assert decision.demand is Demand.IDLE
    assert decision.reason == "unavailable"


def test_home_fallback_respects_use_comfort_off() -> None:
    """With comfort off, a humid home average stays dry-bulb (no cool call)."""
    g = _global(home_temp=24.0, home_humidity=90.0)  # use_comfort defaults False
    assert decide(_cooler(local_temp=None), g).demand is Demand.IDLE
