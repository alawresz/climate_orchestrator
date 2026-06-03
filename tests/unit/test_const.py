"""Pure unit tests that do not require a running Home Assistant."""

from __future__ import annotations

from custom_components.climate_orchestrator.const import DEFAULT_TITLE, DOMAIN


def test_domain_is_stable() -> None:
    """The domain string must not change once published."""
    assert DOMAIN == "climate_orchestrator"


def test_default_title() -> None:
    """The single-instance entry has a human-readable title."""
    assert DEFAULT_TITLE == "Climate Orchestrator"
