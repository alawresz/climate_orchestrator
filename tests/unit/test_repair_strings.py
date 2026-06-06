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

_PKG_DIR = Path(integration_pkg.__file__).parent
_STRINGS = _PKG_DIR / "strings.json"


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
