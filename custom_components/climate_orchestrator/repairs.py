"""Repair-issue helpers: raise and clear the integration's Repairs notices.

Thin, stateless wrappers over the issue registry — every notice here is
edge-safe (creating an existing issue updates it, deleting an absent one is a
no-op), so callers can invoke them every cycle without bookkeeping.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .models import Band, SmartClimateData
    from .settings import RuntimeSettings


def toggle_issue(hass: HomeAssistant, issue_id: str, active: bool, key: str) -> None:
    """Create or clear a static (no-placeholder) repair issue."""
    if active:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key=key,
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


def calibration_issue(
    hass: HomeAssistant, entity_id: str, mode: str, *, missing: bool
) -> None:
    """Raise/clear a repair issue when a TRV lacks its calibration number."""
    issue_id = f"missing_calibration_number_{entity_id}"
    if missing:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="missing_calibration_number",
            translation_placeholders={"entity_id": entity_id, "mode": mode},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


def command_ignored_issue(hass: HomeAssistant, entity_id: str, *, active: bool) -> None:
    """Raise/clear the per-device "commands ignored" repair issue."""
    issue_id = f"device_ignoring_commands_{entity_id}"
    if active:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="device_ignoring_commands",
            translation_placeholders={"entity_id": entity_id},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


def mpc_poor_fit_issue(hass: HomeAssistant, entity_id: str, *, active: bool) -> None:
    """Raise/clear the per-TRV "MPC model fits poorly" repair issue."""
    issue_id = f"mpc_model_poor_fit_{entity_id}"
    if active:
        ir.async_create_issue(
            hass,
            DOMAIN,
            issue_id,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="mpc_model_poor_fit",
            translation_placeholders={"entity_id": entity_id},
        )
    else:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


def capability_issues(
    hass: HomeAssistant,
    settings: RuntimeSettings,
    *,
    acs_configured: bool,
    any_available_ac: bool,
    any_ac_can_heat: bool,
    any_ac_can_dry: bool,
    settled: bool,
) -> None:
    """Surface settings that silently do nothing for want of a capable AC.

    The engine yields the demand, but ``build_command`` drops it when the
    device can't honour it — so these mismatches fail completely silently
    today. Each is gated to avoid false alarms: ``settled`` keeps a restart's
    not-yet-joined devices from tripping the alert, and capability checks only
    consider *available* ACs (an offline one's modes are unknown, not absent).
    """
    # Heating assist is opt-in, so even "no AC selected at all" is a clear
    # mistake. Otherwise: at least one AC is available and none advertise a
    # heat mode (the demand is produced, then thrown away).
    assist_inert = (
        settled
        and settings.ac_heating_assist
        and (not acs_configured or (any_available_ac and not any_ac_can_heat))
    )
    toggle_issue(
        hass, "heating_assist_unavailable", assist_inert, "heating_assist_unavailable"
    )
    # Dew-point guard is on by default, so don't nag radiator-only homes: only
    # flag when an AC *is* configured (and available) yet none can dehumidify.
    dry_inert = (
        settled
        and settings.dew_point_guard
        and acs_configured
        and any_available_ac
        and not any_ac_can_dry
    )
    toggle_issue(hass, "dehumidify_unavailable", dry_inert, "dehumidify_unavailable")
    # The own-room window exemption is opt-in and inert without any AC. This is
    # a pure config check (no capability needed), so no settling gate.
    toggle_issue(
        hass,
        "ac_ignore_window_inert",
        settings.ac_ignore_window and not acs_configured,
        "ac_ignore_window_inert",
    )


def environment_issues(
    hass: HomeAssistant,
    settings: RuntimeSettings,
    data: SmartClimateData,
    base_band: Band,
    *,
    outdoor_sensor: str | None,
    weather_entity: str | None,
    has_devices: bool,
) -> None:
    """Surface misconfigurations that would otherwise fail silently."""
    # An inverted band (cool edge below heat edge) has no neutral zone, so
    # the home would heat below the cool edge and cool above it — running
    # constantly. Flag it rather than burn energy silently.
    toggle_issue(
        hass,
        "inverted_band",
        base_band.cool_edge < base_band.heat_edge,
        "inverted_band",
    )
    # Adaptive comfort is opt-in, so enabling it without an outdoor sensor is
    # a clear mistake. Outdoor gating is on by default, so don't nag about it.
    toggle_issue(
        hass,
        "outdoor_sensor_missing",
        settings.adaptive_cooling_comfort and outdoor_sensor is None,
        "outdoor_sensor_missing",
    )
    # Forecast preconditioning needs a weather entity to read a forecast from.
    toggle_issue(
        hass,
        "weather_forecast_missing",
        settings.forecast_preconditioning and weather_entity is None,
        "weather_forecast_missing",
    )
    # These two are transient right after a restart (sensors haven't
    # reported in yet), so hold them back while still initializing — only
    # raise once warm-up is over and the gap is therefore real.
    settled = not data.initializing
    toggle_issue(
        hass,
        "no_temperature_source",
        settled and has_devices and data.home_avg_temperature is None,
        "no_temperature_source",
    )
    toggle_issue(
        hass,
        "stale_sensor",
        settled and bool(data.stale_sensors),
        "stale_sensor",
    )
