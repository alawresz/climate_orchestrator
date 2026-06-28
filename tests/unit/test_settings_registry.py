"""Pure pins keeping the setting registries and RuntimeSettings in lock-step.

``resolve_settings`` builds ``RuntimeSettings(**values)`` straight from
``NUMBER_SETTINGS``/``SWITCH_SETTINGS``, so these sets must match exactly —
a drift would only surface as a ``TypeError`` on the first control cycle.
"""

from __future__ import annotations

from dataclasses import fields

from custom_components.climate_orchestrator.settings import (
    AC_DRAIN_NUMBER_SETTINGS,
    AC_DRAIN_SWITCH_SETTINGS,
    NUMBER_SETTINGS,
    SWITCH_SETTINGS,
    RuntimeSettings,
)

# Every number/switch setting ``resolve_settings`` reads into ``RuntimeSettings``
# — including the conditionally-created drain entities, whose values are always
# resolved (with a default fallback) even when the entities don't exist.
_ALL_NUMBERS = (*NUMBER_SETTINGS, *AC_DRAIN_NUMBER_SETTINGS)
_ALL_SWITCHES = (*SWITCH_SETTINGS, *AC_DRAIN_SWITCH_SETTINGS)


def test_runtime_settings_fields_match_registries_exactly() -> None:
    registry_keys = (
        {s.key for s in _ALL_NUMBERS}
        | {s.key for s in _ALL_SWITCHES}
        | {"calibration_mode"}
    )
    assert {f.name for f in fields(RuntimeSettings)} == registry_keys


def test_number_and_switch_keys_do_not_collide() -> None:
    assert not {s.key for s in _ALL_NUMBERS} & {s.key for s in _ALL_SWITCHES}


def test_registry_kinds_match_field_types() -> None:
    types_by_name = {f.name: f.type for f in fields(RuntimeSettings)}
    assert all(types_by_name[s.key] == "float" for s in _ALL_NUMBERS)
    assert all(types_by_name[s.key] == "bool" for s in _ALL_SWITCHES)
    assert types_by_name["calibration_mode"] == "str"
