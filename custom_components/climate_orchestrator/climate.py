"""Whole-home climate entity for Climate Orchestrator.

A single climate entity that surfaces the home-wide temperature/humidity
averages and holds the heating/cooling band (two setpoints) + preset + mode.
When a managed AC exposes fan/swing, those are surfaced here and forwarded.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.climate import (
    ATTR_FAN_MODE,
    ATTR_SWING_MODE,
    ATTR_TARGET_TEMP_HIGH,
    ATTR_TARGET_TEMP_LOW,
    SERVICE_SET_FAN_MODE,
    SERVICE_SET_SWING_MODE,
    ClimateEntity,
    ClimateEntityFeature,
    HVACAction,
    HVACMode,
)
from homeassistant.components.climate import (
    DOMAIN as CLIMATE_DOMAIN,
)
from homeassistant.const import ATTR_ENTITY_ID, ATTR_TEMPERATURE, UnitOfTemperature
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_platform
from homeassistant.helpers.restore_state import RestoreEntity
import voluptuous as vol

from .const import (
    DEFAULT_PRESET,
    DEFAULT_PRESETS,
    DOMAIN,
    MAX_TEMP,
    MIN_TEMP,
    PRESET_MANUAL,
    PRESET_MODES,
    SERVICE_RESET_MPC_LEARNING,
    SERVICE_RUN_VALVE_MAINTENANCE,
    TARGET_TEMP_STEP,
)
from .control.adaptive_comfort import adaptive_band
from .control.comfort import effective_temperature
from .control.hysteresis import Demand
from .entity import SmartClimateBaseEntity
from .settings import preset_band
from .util import as_float

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant, State
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .coordinator import SmartClimateConfigEntry, SmartClimateCoordinator

# Writes are funneled through the coordinator; entity updates are pushed
# snapshots, so platform-level update serialization is unnecessary.
PARALLEL_UPDATES = 0

_BASE_FEATURES = (
    ClimateEntityFeature.PRESET_MODE
    | ClimateEntityFeature.TURN_ON
    | ClimateEntityFeature.TURN_OFF
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: SmartClimateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the whole-home climate entity and its maintenance services."""
    async_add_entities([SmartClimateClimateEntity(entry.runtime_data)])

    platform = entity_platform.async_get_current_platform()
    service_schema: dict[Any, Any] = {vol.Optional("trvs"): cv.entity_ids}
    platform.async_register_entity_service(
        SERVICE_RESET_MPC_LEARNING, service_schema, "async_reset_mpc_learning"
    )
    platform.async_register_entity_service(
        SERVICE_RUN_VALVE_MAINTENANCE, service_schema, "async_run_valve_maintenance"
    )


class SmartClimateClimateEntity(SmartClimateBaseEntity, RestoreEntity, ClimateEntity):
    """The single whole-home climate control surface (two setpoints)."""

    _attr_name = None  # use the hub device name
    _attr_icon = "mdi:thermostat"  # mdi:home-thermostat is not a real MDI name
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_preset_modes = PRESET_MODES
    _attr_target_temperature_step = TARGET_TEMP_STEP
    _attr_min_temp = MIN_TEMP
    _attr_max_temp = MAX_TEMP
    _enable_turn_on_off_backwards_compatibility = False

    def __init__(self, coordinator: SmartClimateCoordinator) -> None:
        """Initialise the whole-home climate entity."""
        super().__init__(coordinator)
        self._attr_unique_id = coordinator.entry.entry_id
        self._attr_hvac_mode = HVACMode.OFF
        self._attr_preset_mode = DEFAULT_PRESET
        # Manual band edges (used only when preset == "manual").
        low, high = DEFAULT_PRESETS[DEFAULT_PRESET]
        self._manual_low = low
        self._manual_high = high
        self._attr_fan_mode: str | None = None
        self._attr_swing_mode: str | None = None

    @property
    def _can_heat(self) -> bool:
        """Heating-capable: a TRV is configured, or an AC with heating assist on.

        So an AC-only setup becomes a full heat/cool thermostat once **AC heating
        assist** is enabled (a reversible heat pump), instead of a cool-only one
        whose heat edge could never be reached.
        """
        if self.coordinator.trv_ids:
            return True
        if not self.coordinator.ac_ids:
            return False
        return self.coordinator.current_settings().ac_heating_assist

    @property
    def _can_cool(self) -> bool:
        """Whether any cooling device (an AC) is configured."""
        return bool(self.coordinator.ac_ids)

    @property
    def _dual(self) -> bool:
        """Whether the entity presents a two-setpoint heat/cool band."""
        return self._can_heat and self._can_cool

    @property
    def _on_mode(self) -> HVACMode:
        """The single 'on' mode the configured hardware supports."""
        if self._dual:
            return HVACMode.HEAT_COOL
        if self._can_cool:
            return HVACMode.COOL
        return HVACMode.HEAT

    @property
    def hvac_modes(self) -> list[HVACMode]:
        """Off, plus the mode the configured hardware can actually do.

        Heating-only (TRVs, no AC) -> heat/off; cooling-only (AC, no TRV) ->
        cool/off; both -> heat_cool/off. So a single-purpose setup doesn't show
        an inert second setpoint.
        """
        return [HVACMode.OFF, self._on_mode]

    @property
    def hvac_mode(self) -> HVACMode:
        """Report OFF, or the current on-mode.

        Keeps the value valid even if the supported modes change (e.g. AC heating
        assist toggled on/off).
        """
        if self._attr_hvac_mode == HVACMode.OFF:
            return HVACMode.OFF
        return self._on_mode

    async def async_added_to_hass(self) -> None:
        """Restore the mode, preset, and manual band across restarts."""
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is None:
            return
        if last.state in self.hvac_modes:
            self._attr_hvac_mode = HVACMode(last.state)
        preset = last.attributes.get("preset_mode")
        if preset in PRESET_MODES:
            self._attr_preset_mode = preset
        # as_float: restored attributes come from JSON, which round-trips
        # NaN/Infinity — garbage and non-finite values are both dropped.
        low = as_float(last.attributes.get(ATTR_TARGET_TEMP_LOW))
        high = as_float(last.attributes.get(ATTR_TARGET_TEMP_HIGH))
        temp = as_float(last.attributes.get(ATTR_TEMPERATURE))
        if low is not None and high is not None:
            self._manual_low = low
            self._manual_high = high
        elif temp is not None:
            self._set_single_manual(temp)
        # Reflect the restored mode and re-run control so it takes effect.
        self.async_write_ha_state()
        await self.coordinator.async_request_refresh()

    def _set_single_manual(self, temp: float) -> None:
        """Store a single-setpoint manual value on the edge the hardware uses."""
        if self._can_cool and not self._can_heat:
            self._manual_high = temp
        else:
            self._manual_low = temp

    def _base_band_edges(self) -> tuple[float, float]:
        """User-set band: the preset's live edges or the manual pair.

        For a single-purpose setup the unused edge is pinned to the device
        limit, so the one real setpoint behaves like a normal thermostat target
        (heat below it / cool above it) and the band never looks inverted.
        """
        band = preset_band(
            self.hass,
            self.coordinator.entry.entry_id,
            self._attr_preset_mode or DEFAULT_PRESET,
        )
        heat, cool = band if band is not None else (self._manual_low, self._manual_high)
        if self._can_heat and not self._can_cool:
            return heat, MAX_TEMP
        if self._can_cool and not self._can_heat:
            return MIN_TEMP, cool
        return heat, cool

    def _display_band_edges(self) -> tuple[float, float]:
        """Return the band as shown and controlled.

        This is the base band, with the adaptive-comfort cool-edge relaxation
        folded in when that feature is on.
        Only the cool edge ever moves; the heat edge equals the base. The
        coordinator reads the *base* band back from our attributes, so applying
        the shift here is display-only and never re-applied to itself.
        """
        heat, cool = self._base_band_edges()
        settings = self.coordinator.current_settings()
        if not settings.adaptive_cooling_comfort:
            return heat, cool
        return adaptive_band(
            heat,
            cool,
            self.coordinator.running_mean_outdoor,
            settings.adaptive_cooling_comfort_max_shift,
            bias=settings.adaptive_cooling_comfort_onset_bias,
            response=settings.adaptive_cooling_comfort_response,
        )

    @property
    def target_temperature(self) -> float | None:
        """The single setpoint for a heat-only / cool-only setup (else ``None``).

        Heat-only shows the heat edge; cool-only shows the cool edge (relaxed by
        adaptive comfort). A dual setup uses the low/high range handles instead.
        """
        if self._dual:
            return None
        heat, cool = self._display_band_edges()
        return cool if self._can_cool else heat

    @property
    def target_temperature_low(self) -> float | None:
        """The heating edge (low handle); only on a dual heat/cool setup."""
        return self._display_band_edges()[0] if self._dual else None

    @property
    def target_temperature_high(self) -> float | None:
        """The cooling edge (high handle); only on a dual heat/cool setup."""
        return self._display_band_edges()[1] if self._dual else None

    # --- AC fan/swing discovery ---------------------------------------------

    def _ac_states(self) -> list[State]:
        states = (self.hass.states.get(eid) for eid in self.coordinator.ac_ids)
        return [state for state in states if state is not None]

    def _common_modes(self, attribute: str) -> list[str] | None:
        """Modes supported by every AC that advertises them (order preserved)."""
        lists = [
            modes
            for state in self._ac_states()
            if (modes := state.attributes.get(attribute))
        ]
        if not lists:
            return None
        common = set(lists[0]).intersection(*(set(modes) for modes in lists[1:]))
        return [mode for mode in lists[0] if mode in common] or None

    @property
    def supported_features(self) -> ClimateEntityFeature:
        """Report the supported features.

        A range setpoint for dual setups, a single one otherwise; plus fan/swing
        when a managed AC supports them.
        """
        if self._dual:
            features = _BASE_FEATURES | ClimateEntityFeature.TARGET_TEMPERATURE_RANGE
        else:
            features = _BASE_FEATURES | ClimateEntityFeature.TARGET_TEMPERATURE
        if self._common_modes("fan_modes"):
            features |= ClimateEntityFeature.FAN_MODE
        if self._common_modes("swing_modes"):
            features |= ClimateEntityFeature.SWING_MODE
        return features

    @property
    def fan_modes(self) -> list[str] | None:
        """Fan modes common to the managed ACs."""
        return self._common_modes("fan_modes")

    @property
    def swing_modes(self) -> list[str] | None:
        """Swing modes common to the managed ACs."""
        return self._common_modes("swing_modes")

    @property
    def fan_mode(self) -> str | None:
        """Last set fan mode, else the first AC's current fan mode."""
        if self._attr_fan_mode is not None:
            return self._attr_fan_mode
        states = self._ac_states()
        return states[0].attributes.get("fan_mode") if states else None

    @property
    def swing_mode(self) -> str | None:
        """Last set swing mode, else the first AC's current swing mode."""
        if self._attr_swing_mode is not None:
            return self._attr_swing_mode
        states = self._ac_states()
        return states[0].attributes.get("swing_mode") if states else None

    # --- State ---------------------------------------------------------------

    @property
    def available(self) -> bool:
        """Stay available while any device or temperature source remains."""
        if not super().available:
            return False
        data = self.coordinator.data
        return bool(data.available_devices) or data.home_avg_temperature is not None

    @property
    def current_temperature(self) -> float | None:
        """Report the home-wide temperature.

        The feels-like value when comfort targeting is on, so the card matches
        what the control loop actually judges against. The raw dry-bulb average
        is always kept in ``dry_bulb_temperature``.
        """
        data = self.coordinator.data
        temp = data.home_avg_temperature
        if temp is None:
            return None
        settings = self.coordinator.current_settings()
        if settings.comfort_index_targeting and data.home_avg_humidity is not None:
            return effective_temperature(
                temp,
                data.home_avg_humidity,
                use_comfort=True,
                influence=settings.comfort_humidity_influence,
            )
        return temp

    @property
    def current_humidity(self) -> float | None:
        """Home-wide average humidity."""
        return self.coordinator.data.home_avg_humidity

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Surface the underlying values behind any comfort/adaptive display.

        ``current_temperature`` may show the feels-like temperature and
        ``target_temp_high`` the adaptive-comfort-relaxed cool edge; these
        attributes always carry the raw dry-bulb temperature and the user-set
        base band. The coordinator reads the base band back from here, so the
        adaptive shift is never compounded on itself.
        """
        base_low, base_high = self._base_band_edges()
        attrs: dict[str, Any] = {
            "base_target_temp_low": base_low,
            "base_target_temp_high": base_high,
        }
        dry_bulb = self.coordinator.data.home_avg_temperature
        if dry_bulb is not None:
            attrs["dry_bulb_temperature"] = dry_bulb
        return attrs

    @property
    def hvac_action(self) -> HVACAction:
        """Aggregate action: heating/cooling if any device is doing so."""
        if self._attr_hvac_mode == HVACMode.OFF:
            return HVACAction.OFF
        demands = {d.demand for d in self.coordinator.last_decisions.values()}
        if Demand.HEAT in demands:
            return HVACAction.HEATING
        if Demand.COOL in demands:
            return HVACAction.COOLING
        return HVACAction.IDLE

    # --- Commands ------------------------------------------------------------

    async def _apply_and_control(self) -> None:
        """Persist the new desired state, then run a control cycle."""
        self.async_write_ha_state()
        await self.coordinator.async_refresh()

    async def async_set_temperature(self, **kwargs: Any) -> None:
        """Set the setpoint(s) and switch to the manual preset.

        Dual setups take the two range handles; a single-purpose setup takes the
        one ``temperature`` value and applies it to the edge it controls.
        """
        if self._dual:
            low = kwargs.get(ATTR_TARGET_TEMP_LOW)
            high = kwargs.get(ATTR_TARGET_TEMP_HIGH)
            if low is None or high is None:
                return
            self._manual_low = float(low)
            self._manual_high = float(high)
        else:
            temp = kwargs.get(ATTR_TEMPERATURE)
            if temp is None:
                return
            self._set_single_manual(float(temp))
        self._attr_preset_mode = PRESET_MANUAL
        await self._apply_and_control()

    async def async_set_hvac_mode(self, hvac_mode: HVACMode) -> None:
        """Set the HVAC mode."""
        self._attr_hvac_mode = hvac_mode
        await self._apply_and_control()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        """Select a preset; its (editable) band edges then drive the setpoints."""
        self._attr_preset_mode = preset_mode
        await self._apply_and_control()

    async def async_set_fan_mode(self, fan_mode: str) -> None:
        """Forward a fan mode to every AC that supports it."""
        await self._forward_to_acs(
            SERVICE_SET_FAN_MODE, ATTR_FAN_MODE, fan_mode, "fan_modes"
        )
        self._attr_fan_mode = fan_mode
        self.async_write_ha_state()

    async def async_set_swing_mode(self, swing_mode: str) -> None:
        """Forward a swing mode to every AC that supports it."""
        await self._forward_to_acs(
            SERVICE_SET_SWING_MODE, ATTR_SWING_MODE, swing_mode, "swing_modes"
        )
        self._attr_swing_mode = swing_mode
        self.async_write_ha_state()

    async def _forward_to_acs(
        self, service: str, key: str, value: str, modes_attr: str
    ) -> None:
        for state in self._ac_states():
            if value in (state.attributes.get(modes_attr) or []):
                await self.hass.services.async_call(
                    CLIMATE_DOMAIN,
                    service,
                    {ATTR_ENTITY_ID: state.entity_id, key: value},
                    blocking=True,
                )

    async def async_reset_mpc_learning(self, trvs: list[str] | None = None) -> None:
        """Service: forget the learned MPC model for some/all TRVs."""
        await self.coordinator.async_reset_mpc(trvs)

    async def async_run_valve_maintenance(self, trvs: list[str] | None = None) -> None:
        """Service: exercise some/all TRV valves (full open then closed)."""
        if not await self.coordinator.async_run_valve_maintenance(trvs):
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="no_maintenance_valves",
            )

    async def async_turn_on(self) -> None:
        """Turn the climate entity on into the mode its hardware supports."""
        await self.async_set_hvac_mode(self._on_mode)

    async def async_turn_off(self) -> None:
        """Turn the climate entity off."""
        await self.async_set_hvac_mode(HVACMode.OFF)
