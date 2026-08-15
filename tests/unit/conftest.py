"""Snapshot wiring for the pure unit tests.

Deliberately not in ``tests/conftest.py``: that module keeps ``tests/unit/``
free of the Home Assistant test harness (see its docstring), and Home
Assistant's syrupy extension would drag it in. The snapshots here hold plain
dicts of floats, so stock Amber serialises them identically.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from syrupy.extensions.amber import AmberSnapshotExtension

if TYPE_CHECKING:
    from syrupy.assertion import SnapshotAssertion
    from syrupy.location import PyTestLocation


class _ColocatedAmber(AmberSnapshotExtension):
    """Keep snapshots in ``snapshots/`` next to the test file.

    Which directory holds them has moved twice under us: syrupy defaults to
    ``__snapshots__``; Home Assistant's extension overrides that to plain
    ``snapshots``; and newer pytest-homeassistant-custom-component no longer
    applies its extension for you, handing the default back. Each move made
    the committed ``.ambr`` invisible and every snapshot test fail with
    "snapshot does not exist". Pinning the directory here means a dependency
    bump can't relocate it again.
    """

    @classmethod
    def dirname(cls, *, test_location: PyTestLocation) -> str:
        """Return ``snapshots/`` beside the test file, regardless of defaults."""
        return str(Path(test_location.filepath).parent / "snapshots")


@pytest.fixture
def snapshot(snapshot: SnapshotAssertion) -> SnapshotAssertion:
    """Amber snapshots, pinned to ``snapshots/`` beside the test."""
    return snapshot.use_extension(_ColocatedAmber)
