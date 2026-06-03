"""Update minimization: compute only the writes that actually change state.

A service call is emitted only when the device isn't already in the requested
mode, or the target differs by at least one step (DESIGN.md §6.3). Pure.
"""

from __future__ import annotations

from .model import DeviceCommand, DeviceState, Mode, Writes


def reconcile(current: DeviceState, command: DeviceCommand, *, step: float) -> Writes:
    """Return the minimal writes to bring ``current`` to ``command``."""
    set_mode = (
        command.hvac_mode if current.hvac_mode != command.hvac_mode.value else None
    )

    set_temperature: float | None = None
    if (
        command.target_temp is not None
        and command.hvac_mode is not Mode.OFF
        and (
            current.target_temp is None
            or abs(current.target_temp - command.target_temp) >= step
        )
    ):
        set_temperature = command.target_temp

    return Writes(set_hvac_mode=set_mode, set_temperature=set_temperature)
