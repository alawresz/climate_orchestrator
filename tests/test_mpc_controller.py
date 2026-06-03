"""End-to-end tests for the MPC controller on a synthetic room."""

from __future__ import annotations

from custom_components.climate_orchestrator.control.mpc.controller import MpcController
from custom_components.climate_orchestrator.control.mpc.model import (
    ThermalParams,
    predict_step,
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
