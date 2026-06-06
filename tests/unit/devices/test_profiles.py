"""Unit tests for DeviceProfile parsing and resolution (no hass needed)."""

from __future__ import annotations

from custom_components.climate_orchestrator.const import (
    MAX_TEMP,
    MIN_TEMP,
    TARGET_TEMP_STEP,
)
from custom_components.climate_orchestrator.devices.profiles import (
    GENERIC,
    SONOFF_TRVZB,
    DeviceProfile,
    resolve_profile,
)
from custom_components.climate_orchestrator.devices.trv import (
    LOCAL_CALIBRATION_HINTS,
    VALVE_OPENING_HINTS,
)

_HEATPUMP_ATTRS = {
    "hvac_modes": ["off", "heat", "cool", "dry"],
    "current_temperature": 19.5,
    "temperature": 21.0,
    "min_temp": 5.0,
    "max_temp": 30.0,
    "target_temp_step": 0.1,
}


def test_generic_read_uses_standard_attributes() -> None:
    """The generic profile reads the standard climate attribute names."""
    state = GENERIC.read("heat", _HEATPUMP_ATTRS)
    assert state.available is True
    assert state.hvac_mode == "heat"
    assert state.current_temp == 19.5
    assert state.target_temp == 21.0


def test_generic_read_treats_unavailable_as_offline() -> None:
    """An unavailable/unknown state reads as a fully empty device state."""
    for raw in (None, "unavailable", "unknown"):
        state = GENERIC.read(raw, {})
        assert state.available is False
        assert state.hvac_mode is None
        assert state.current_temp is None
        assert state.target_temp is None


def test_generic_read_drops_non_finite_values() -> None:
    """A NaN reading is dropped, not passed through (shared as_float guard)."""
    state = GENERIC.read("heat", {"current_temperature": "nan", "temperature": "x"})
    assert state.current_temp is None
    assert state.target_temp is None


def test_generic_capabilities_from_modes_and_limits() -> None:
    """Capabilities derive from hvac_modes and the reported limits."""
    caps = GENERIC.capabilities(_HEATPUMP_ATTRS)
    assert (caps.can_heat, caps.can_cool, caps.can_dry) == (True, True, True)
    assert caps.min_temp == 5.0
    assert caps.max_temp == 30.0
    assert caps.target_step == 0.1


def test_generic_capabilities_fall_back_to_constants() -> None:
    """Missing limits fall back to the integration's defaults."""
    caps = GENERIC.capabilities({})
    assert caps.can_heat is False
    assert caps.min_temp == MIN_TEMP
    assert caps.max_temp == MAX_TEMP
    assert caps.target_step == TARGET_TEMP_STEP


def test_custom_attribute_names_are_honoured() -> None:
    """A profile can point reads at non-standard attribute names."""
    profile = DeviceProfile(
        name="weird",
        current_temp_attr="room_temp",
        target_temp_attr="setpoint",
    )
    state = profile.read("heat", {"room_temp": 18.0, "setpoint": 22.0})
    assert state.current_temp == 18.0
    assert state.target_temp == 22.0


def test_hint_resolution_prefers_profile_then_config() -> None:
    """Profile hints win when set; otherwise the configured hints pass through."""
    configured = ("valve_opening_degree",)
    assert GENERIC.resolve_valve_hints(configured) == configured
    assert GENERIC.resolve_calibration_hints(configured) == configured

    profile = DeviceProfile(
        name="acme",
        valve_hints=("acme_valve",),
        calibration_hints=("acme_offset",),
    )
    assert profile.resolve_valve_hints(configured) == ("acme_valve",)
    assert profile.resolve_calibration_hints(configured) == ("acme_offset",)


def test_resolve_profile_defaults_to_generic_for_unknown_hardware() -> None:
    """An unrecognised device identity resolves to the generic profile."""
    assert (
        resolve_profile(integration="mqtt", manufacturer="Acme", model="Widget")
        is GENERIC
    )
    assert resolve_profile(integration=None, manufacturer=None, model=None) is GENERIC


def test_sonoff_trvzb_matches_by_model_across_integrations() -> None:
    """The TRVZB resolves by model whether Z2M or ZHA reports the make."""
    assert (
        resolve_profile(integration="mqtt", manufacturer="SONOFF", model="TRVZB")
        is SONOFF_TRVZB
    )
    assert (
        resolve_profile(integration="zha", manufacturer="eWeLink", model="TRVZB")
        is SONOFF_TRVZB
    )


def test_sonoff_profile_carries_the_canonical_discovery_hints() -> None:
    """Its hints equal the shared defaults, so discovery is unchanged."""
    configured = ("user_custom_hint",)
    assert SONOFF_TRVZB.resolve_valve_hints(configured) == VALVE_OPENING_HINTS
    assert SONOFF_TRVZB.resolve_calibration_hints(configured) == LOCAL_CALIBRATION_HINTS
