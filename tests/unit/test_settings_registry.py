"""Pure pins keeping the setting registries and RuntimeSettings in lock-step.

``resolve_settings`` builds ``RuntimeSettings(**values)`` straight from
``NUMBER_SETTINGS``/``SWITCH_SETTINGS``, so these sets must match exactly —
a drift would only surface as a ``TypeError`` on the first control cycle.
"""

from __future__ import annotations

from dataclasses import fields

from custom_components.climate_orchestrator.settings import (
    NUMBER_SETTINGS,
    SWITCH_SETTINGS,
    RuntimeSettings,
)


def test_runtime_settings_fields_match_registries_exactly() -> None:
    registry_keys = (
        {s.key for s in NUMBER_SETTINGS}
        | {s.key for s in SWITCH_SETTINGS}
        | {"calibration_mode"}
    )
    assert {f.name for f in fields(RuntimeSettings)} == registry_keys


def test_number_and_switch_keys_do_not_collide() -> None:
    assert not {s.key for s in NUMBER_SETTINGS} & {s.key for s in SWITCH_SETTINGS}


def test_registry_kinds_match_field_types() -> None:
    types_by_name = {f.name: f.type for f in fields(RuntimeSettings)}
    assert all(types_by_name[s.key] == "float" for s in NUMBER_SETTINGS)
    assert all(types_by_name[s.key] == "bool" for s in SWITCH_SETTINGS)
    assert types_by_name["calibration_mode"] == "str"
