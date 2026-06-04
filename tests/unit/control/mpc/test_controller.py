"""End-to-end tests for the MPC controller on a synthetic room."""

from __future__ import annotations

import math

import pytest

from custom_components.climate_orchestrator.control.mpc.controller import (
    MAX_SAMPLE_DT_MIN,
    MpcController,
    preconditioned_valve_pct,
)
from custom_components.climate_orchestrator.control.mpc.model import (
    MAX_GAIN,
    Sample,
    ThermalParams,
    predict_step,
)
from custom_components.climate_orchestrator.control.mpc.observer import (
    MAX_VARIANCE,
    MEASUREMENT_VAR,
    KalmanState,
)


def test_controller_drives_temperature_to_target() -> None:
    """Closed loop on a simulated room converges near the target."""
    true = ThermalParams(gain=0.25, loss=0.02)  # equilibrium reachable
    controller = MpcController()

    temp, outdoor, target, dt, valve = 17.0, 15.0, 21.0, 1.0, 0.0
    for _ in range(200):
        controller.observe(temp=temp, valve=valve, outdoor=outdoor, dt=dt)
        valve = (
            controller.compute_valve_pct(
                temp=temp, target=target, outdoor=outdoor, dt=dt
            )
            / 100.0
        )
        temp = predict_step(temp, valve, outdoor, true, dt)

    assert abs(temp - target) < 0.7


def test_persistence_round_trip() -> None:
    """Learned state survives a serialise/restore cycle."""
    controller = MpcController(ThermalParams(gain=0.3, loss=0.03))
    controller.observe(temp=18.0, valve=1.0, outdoor=5.0, dt=1.0)
    controller.observe(temp=18.4, valve=1.0, outdoor=5.0, dt=1.0)

    restored = MpcController.from_dict(controller.to_dict())
    assert restored.params == controller.params
    assert len(restored.history) == len(controller.history)


# --- mutation-hardening: boundary/exact-value pins (mutmut survivors) ---


def test_compute_valve_pct_full_demand_and_ceiling() -> None:
    c = MpcController()
    assert c.compute_valve_pct(temp=15.0, target=25.0, outdoor=15.0, dt=5.0) == 100.0
    assert (
        c.compute_valve_pct(
            temp=15.0, target=25.0, outdoor=15.0, dt=5.0, max_opening_pct=50.0
        )
        == 50.0
    )


def test_compute_valve_pct_horizon_and_rounding() -> None:
    c = MpcController()
    short = c.compute_valve_pct(temp=20.0, target=20.2, outdoor=20.0, dt=5.0, horizon=1)
    long = c.compute_valve_pct(temp=20.0, target=20.2, outdoor=20.0, dt=5.0)
    assert short == 40.0
    assert long == 10.3  # one-decimal rounding of ~10.2787
    assert isinstance(short, float)


def test_history_is_bounded_by_max_history() -> None:
    c = MpcController(max_history=3)
    for k in range(5):
        c.observe(temp=20.0 + k * 0.1, valve=0.5, outdoor=10.0, dt=1.0)
    assert len(c.history) == 3


def test_observe_requires_strictly_positive_dt() -> None:
    c = MpcController()
    c.observe(temp=20.0, valve=0.5, outdoor=10.0, dt=0.0)
    c.observe(temp=20.1, valve=0.5, outdoor=10.0, dt=0.0)
    assert len(c.history) == 0
    c2 = MpcController()
    c2.observe(temp=20.0, valve=0.5, outdoor=10.0, dt=0.5)
    c2.observe(temp=20.1, valve=0.5, outdoor=10.0, dt=0.5)
    assert len(c2.history) == 1


def test_observe_fits_at_exactly_min_samples() -> None:
    """The 6th sample triggers identification (>=, not >)."""
    c = MpcController()
    temp = 20.0
    for _ in range(7):
        c.observe(temp=temp, valve=1.0, outdoor=temp, dt=1.0)
        temp += 0.3  # pure gain 0.3 signal (loss term zeroed via outdoor==temp)
    assert len(c.history) == 6
    assert c.params.gain == pytest.approx(0.3, abs=0.05)


def test_observe_passes_current_params_as_prior() -> None:
    """Neutral data keeps the controller's own (custom) prior, not the default."""
    c = MpcController(ThermalParams(gain=0.3, loss=0.07))
    for _ in range(7):
        c.observe(temp=20.0, valve=0.0, outdoor=20.0, dt=1.0)
    assert c.params.gain == pytest.approx(0.3, abs=0.02)
    assert c.params.loss == pytest.approx(0.07, abs=0.02)


def test_fit_rmse_exact_value() -> None:
    c = MpcController(ThermalParams(gain=0.1, loss=0.0))
    deltas = [0.1, 0.2, 0.3, 0.1, 0.2, 0.3]
    temp = 20.0
    for d in deltas:
        c.history.append(
            Sample(dt=1.0, temp=temp, next_temp=temp + d, valve=0.0, outdoor=temp)
        )
        temp += d
    assert c.fit_rmse() == pytest.approx(
        math.sqrt(sum(d * d for d in deltas) / 6), abs=1e-9
    )


# --- preconditioned_valve_pct: forecast overlay can only raise the valve ----


def _params_controller() -> MpcController:
    return MpcController(ThermalParams(gain=0.1, loss=0.01))


def test_precondition_none_passes_base_through() -> None:
    ctrl = _params_controller()
    base = ctrl.compute_valve_pct(temp=20.5, target=21.0, outdoor=25.0, dt=5.0)
    assert (
        preconditioned_valve_pct(
            ctrl, temp=20.5, target=21.0, outdoor=25.0, series=None, dt=5.0
        )
        == base
        == 0.0
    )


def test_precondition_cold_forecast_raises_valve() -> None:
    """Warm now (valve shut), cold spell coming -> pre-heat at full opening."""
    ctrl = _params_controller()
    assert (
        preconditioned_valve_pct(
            ctrl, temp=20.5, target=21.0, outdoor=25.0, series=[5.0] * 6, dt=5.0
        )
        == 100.0
    )


def test_precondition_warm_forecast_never_lowers_valve() -> None:
    """Cold now (full heat), warm spell coming -> the present still wins."""
    ctrl = _params_controller()
    assert (
        preconditioned_valve_pct(
            ctrl, temp=20.5, target=21.0, outdoor=5.0, series=[25.0] * 6, dt=5.0
        )
        == 100.0
    )


# --- Kalman wiring: observe() maintains the filtered planning estimate ------


def test_estimate_is_none_until_first_observation() -> None:
    assert _params_controller().estimated_temperature is None


def test_first_measurement_seeds_the_estimate() -> None:
    ctrl = _params_controller()
    ctrl.observe(temp=20.0, valve=0.5, outdoor=10.0, dt=5.0)
    assert ctrl.estimated_temperature == 20.0


def test_estimate_damps_a_measurement_spike() -> None:
    """A +2K sensor spike is heavily damped in the planning estimate."""
    ctrl = _params_controller()
    ctrl.observe(temp=20.0, valve=0.5, outdoor=10.0, dt=5.0)
    ctrl.observe(temp=20.0, valve=0.5, outdoor=10.0, dt=5.0)
    steady = ctrl.estimated_temperature
    assert steady == pytest.approx(19.8838559814, abs=1e-9)
    ctrl.observe(temp=22.0, valve=0.5, outdoor=10.0, dt=5.0)
    spiked = ctrl.estimated_temperature
    assert spiked == pytest.approx(20.6381782514, abs=1e-9)
    # Strictly between the model's expectation and the spiky reading.
    assert steady < spiked < 22.0


def test_kalman_state_survives_persistence_roundtrip() -> None:
    ctrl = _params_controller()
    ctrl.observe(temp=20.0, valve=0.5, outdoor=10.0, dt=5.0)
    ctrl.observe(temp=21.0, valve=0.5, outdoor=10.0, dt=5.0)
    clone = MpcController.from_dict(ctrl.to_dict())
    assert clone.kalman == ctrl.kalman


def test_legacy_payload_without_kalman_restores_unfiltered() -> None:
    """Stores written before the observer wiring load cleanly."""
    legacy = MpcController.from_dict({"gain": 0.1, "loss": 0.01})
    assert legacy.kalman is None
    assert legacy.estimated_temperature is None


def test_from_dict_rejects_malformed_parameters() -> None:
    """Corrupt persisted state raises instead of building a broken controller."""
    with pytest.raises(TypeError):
        MpcController.from_dict({"gain": "garbage", "loss": 0.01})
    with pytest.raises(TypeError):
        MpcController.from_dict({"loss": 0.01})  # gain missing entirely


def test_observe_with_zero_dt_updates_without_prediction() -> None:
    """dt=0 has no transition to project across — measurement-only correction."""
    ctrl = _params_controller()
    ctrl.observe(temp=20.0, valve=0.5, outdoor=10.0, dt=5.0)
    ctrl.observe(temp=20.0, valve=0.5, outdoor=10.0, dt=5.0)
    ctrl.observe(temp=20.0, valve=0.5, outdoor=10.0, dt=0.0)
    assert ctrl.kalman is not None
    assert ctrl.kalman.variance == pytest.approx(0.0139485628, abs=1e-9)


def test_observe_with_subminute_dt_still_predicts() -> None:
    """Any positive dt projects the estimate forward; only dt <= 0 skips."""
    ctrl = _params_controller()
    ctrl.observe(temp=20.0, valve=0.5, outdoor=10.0, dt=5.0)
    ctrl.observe(temp=20.0, valve=0.5, outdoor=10.0, dt=5.0)
    ctrl.observe(temp=20.0, valve=0.5, outdoor=10.0, dt=0.5)
    assert ctrl.kalman is not None
    assert ctrl.kalman.variance == pytest.approx(0.0175291386, abs=1e-9)


def test_precondition_sees_cold_beyond_the_default_horizon() -> None:
    """A 12-step series is optimised over 12 steps, not the default 6 —
    otherwise a cold spell arriving after 6 steps would be invisible."""
    ctrl = _params_controller()
    series = [25.0] * 6 + [5.0] * 6
    pct = preconditioned_valve_pct(
        ctrl, temp=20.5, target=21.0, outdoor=25.0, series=series, dt=5.0
    )
    assert pct == pytest.approx(42.6, abs=2.0)


# --- production hardening: garbage inputs, long gaps, restore validation -----


def test_non_finite_observation_is_ignored() -> None:
    ctrl = MpcController()
    for _ in range(8):
        ctrl.observe(temp=20.0, valve=0.5, outdoor=10.0, dt=1.0)
    before = (ctrl.params, len(ctrl.history), ctrl.kalman)
    ctrl.observe(temp=float("nan"), valve=0.5, outdoor=10.0, dt=1.0)
    ctrl.observe(temp=20.0, valve=float("inf"), outdoor=10.0, dt=1.0)
    assert (ctrl.params, len(ctrl.history), ctrl.kalman) == before


def test_long_gap_reanchors_instead_of_learning() -> None:
    """A 6 h freeze is not a usable transition: no sample, estimate re-seeded."""
    ctrl = MpcController()
    for _ in range(8):
        ctrl.observe(temp=20.0, valve=0.5, outdoor=10.0, dt=1.0)
    n_hist = len(ctrl.history)
    ctrl.observe(temp=25.0, valve=0.5, outdoor=10.0, dt=360.0)
    assert len(ctrl.history) == n_hist
    assert ctrl.kalman is not None
    assert ctrl.kalman.temp == 25.0
    assert ctrl.kalman.variance == MEASUREMENT_VAR


def test_valve_pct_clamped_to_hardware_range() -> None:
    """Even an absurd max_opening_pct never commands more than 100%."""
    pct = MpcController().compute_valve_pct(
        temp=15.0, target=25.0, outdoor=-10.0, dt=1.0, max_opening_pct=500.0
    )
    assert 0.0 <= pct <= 100.0


def test_from_dict_rejects_non_finite_params() -> None:
    """json round-trips NaN, so a corrupt store can hand back 'numbers'."""
    with pytest.raises(TypeError):
        MpcController.from_dict({"gain": float("nan"), "loss": 0.01})


def test_from_dict_sanitises_history_kalman_and_params() -> None:
    good = {"dt": 1.0, "temp": 20.0, "next_temp": 20.1, "valve": 0.5, "outdoor": 5.0}
    bad = dict(good, temp=float("nan"))
    ctrl = MpcController.from_dict(
        {
            "gain": 5.0,  # past the fit bound -> clamped
            "loss": 0.01,
            "history": [good, bad],  # the nan sample is dropped
            "kalman": {"temp": 20.0, "variance": 1e9},  # variance capped
        }
    )
    assert ctrl.params.gain == MAX_GAIN
    assert len(ctrl.history) == 1
    assert ctrl.kalman is not None
    assert ctrl.kalman.variance == MAX_VARIANCE


def test_from_dict_drops_non_finite_kalman_state() -> None:
    ctrl = MpcController.from_dict(
        {"gain": 0.1, "loss": 0.01, "kalman": {"temp": float("inf"), "variance": 0.04}}
    )
    assert ctrl.kalman is None  # re-learns from the next measurement


def test_observe_bridges_exactly_at_the_dt_cap() -> None:
    """dt == MAX_SAMPLE_DT_MIN is still a usable transition (mutation pin).

    Pins both boundary comparisons: the sample is learned (``<=`` not ``<``)
    and the estimate is projected rather than re-anchored (``>`` not ``>=``).
    """
    ctrl = MpcController()
    ctrl.observe(temp=20.0, valve=0.5, outdoor=10.0, dt=1.0)
    n = len(ctrl.history)

    ctrl.observe(temp=20.5, valve=0.5, outdoor=10.0, dt=MAX_SAMPLE_DT_MIN)
    assert len(ctrl.history) == n + 1  # learned, not skipped
    assert ctrl.kalman is not None
    assert ctrl.kalman.variance != MEASUREMENT_VAR  # projected, not re-anchored


@pytest.mark.parametrize(
    ("dt", "bridges"),
    [
        (MAX_SAMPLE_DT_MIN - 0.001, True),
        (MAX_SAMPLE_DT_MIN, True),
        (MAX_SAMPLE_DT_MIN + 0.001, False),
    ],
    ids=["just-under", "exactly-at", "just-over"],
)
def test_dt_cap_boundary_separates_bridge_from_reanchor(dt, bridges) -> None:
    """Pin both comparisons around the cap: <= learns/projects, > re-anchors."""
    ctrl = MpcController()
    ctrl.observe(temp=20.0, valve=0.5, outdoor=10.0, dt=1.0)
    n = len(ctrl.history)

    ctrl.observe(temp=20.5, valve=0.5, outdoor=10.0, dt=dt)
    assert (len(ctrl.history) == n + 1) is bridges
    assert ctrl.kalman is not None
    anchored = ctrl.kalman.variance == MEASUREMENT_VAR and ctrl.kalman.temp == 20.5
    assert anchored is not bridges


def test_kalman_recovers_after_cap_and_reanchor() -> None:
    """Saturated variance -> long-gap re-anchor -> normal steps shrink it again."""
    ctrl = MpcController()
    ctrl.observe(temp=20.0, valve=0.5, outdoor=10.0, dt=1.0)
    ctrl.kalman = KalmanState(temp=20.0, variance=MAX_VARIANCE)  # saturated

    ctrl.observe(temp=25.0, valve=0.5, outdoor=10.0, dt=500.0)  # unbridgeable gap
    assert ctrl.kalman == KalmanState(temp=25.0, variance=MEASUREMENT_VAR)

    ctrl.observe(temp=25.1, valve=0.5, outdoor=10.0, dt=1.0)
    assert ctrl.kalman.variance < MEASUREMENT_VAR  # converging again


def test_negative_max_opening_yields_closed_valve() -> None:
    pct = MpcController().compute_valve_pct(
        temp=15.0, target=25.0, outdoor=-10.0, dt=1.0, max_opening_pct=-50.0
    )
    assert pct == 0.0
