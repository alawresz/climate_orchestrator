"""Guard: every repair key raised in code has a strings.json definition.

A typo'd ``translation_key`` (or a ``toggle_issue`` key) would ship a repair
notice with no localized title/description — invisible to ruff, mypy, and the
strings.json/en.json sync check. This pins the two together.
"""

from __future__ import annotations

import json
from pathlib import Path
import re

import custom_components.climate_orchestrator as integration_pkg
from custom_components.climate_orchestrator.repairs import _GLOBAL_ISSUE_IDS

_PKG_DIR = Path(integration_pkg.__file__).parent
_STRINGS = _PKG_DIR / "strings.json"

# Issue ids carrying a per-device entity suffix (cleared per entity_id, so not
# in _GLOBAL_ISSUE_IDS). These are the static prefixes of those issue ids.
_PER_DEVICE_ISSUE_KEYS = frozenset(
    {"missing_calibration_number", "device_ignoring_commands", "mpc_model_poor_fit"}
)


def _repair_keys_used() -> set[str]:
    """Every repair translation key referenced in code.

    Two sources, kept narrow so entity ``translation_key`` assignments (which
    live under strings.json ``entity``, not ``issues``) aren't swept in:

    * ``translation_key="..."`` inside ``repairs.py`` — every
      ``ir.async_create_issue`` lives there (calibration / command-ignored /
      mpc-poor-fit).
    * the ``key`` positional of ``toggle_issue(hass, issue_id, active, key)``,
      package-wide — raised from both repairs.py and the coordinator.
    """
    repairs_src = (_PKG_DIR / "repairs.py").read_text(encoding="utf-8")
    keys = set(re.findall(r'translation_key="([^"]+)"', repairs_src))
    for path in _PKG_DIR.rglob("*.py"):
        src = path.read_text(encoding="utf-8")
        keys.update(
            re.findall(r'toggle_issue\(\s*hass,\s*"[^"]+",[^,]+,\s*"([^"]+)"', src)
        )
    return keys


def test_every_repair_key_is_defined_in_strings() -> None:
    """Keys raised in code must exist under strings.json ``issues``."""
    defined = set(json.loads(_STRINGS.read_text(encoding="utf-8"))["issues"])
    used = _repair_keys_used()
    assert used, "scan found no repair keys — the regex has drifted from the code"
    missing = used - defined
    assert not missing, f"repair keys with no strings.json entry: {sorted(missing)}"


def test_every_issue_is_either_global_or_per_device() -> None:
    """Every defined issue is cleared on teardown via one of the two lists.

    Guards ``clear_all_issues``: a new whole-entry repair added to strings.json
    but forgotten in ``_GLOBAL_ISSUE_IDS`` would otherwise orphan on unload.
    """
    defined = set(json.loads(_STRINGS.read_text(encoding="utf-8"))["issues"])
    accounted = set(_GLOBAL_ISSUE_IDS) | _PER_DEVICE_ISSUE_KEYS
    assert not defined - accounted, (
        "issues neither in _GLOBAL_ISSUE_IDS nor per-device (won't clear on "
        f"unload): {sorted(defined - accounted)}"
    )
