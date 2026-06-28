"""Sensors for Climate Orchestrator.

Two families:

* **Home-wide measurements** (no entity category, shown under *Sensors*): the
  whole-home temperature/humidity averages and the temperature slope (K/min).
* **Per-TRV MPC diagnostics** (diagnostic category): one learning-status enum
  per TRV carrying the learned model (gain, loss, fit error, sample count) as
  attributes — surfacing what each radiator's model has figured out without a
  recorder series per number. Only meaningful in ``mpc`` calibration mode;
  otherwise it reads ``idle`` with no attributes.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfTemperature

from .const import MPC_MIN_SAMPLES as MIN_SAMPLES
from .control.comfort import effective_temperature
from .entity import SmartClimateBaseEntity
from .models import HomeAvgSource, SmartClimateData, Status

if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from .control.mpc.controller import MpcController
    from .coordinator import SmartClimateConfigEntry, SmartClimateCoordinator

# Writes are funneled through the coordinator; entity updates are pushed
# snapshots, so platform-level update serialization is unnecessary.
PARALLEL_UPDATES = 0

_KELVIN_PER_MINUTE = "K/min"

_REASON_OPTIONS = [
    "off",
    "idle",
    "heating",
    "cooling",
    "dehumidifying",
    "frost_protection",
    "window_open",
    "outdoor_gating",
    "manual_override",
    "drain_full",
    "unavailable",
    "no_data",
]

_LEARNING_IDLE = "idle"
_LEARNING_LEARNING = "learning"
_LEARNING_READY = "ready"
_LEARNING_OPTIONS = [_LEARNING_IDLE, _LEARNING_LEARNING, _LEARNING_READY]

_STATUS_OPTIONS = [s.value for s in Status]

# Headline for the home-average source diagnostic: when temperature and
# humidity disagree (e.g. only one override configured), report "mixed" and
# carry the per-reading detail in the attributes.
_HOME_AVG_SOURCE_OPTIONS = [*[s.value for s in HomeAvgSource], "mixed"]


def _home_avg_source(data: SmartClimateData) -> str:
    """Combine the temperature + humidity sources into one headline."""
    if data.home_temp_source is data.home_humidity_source:
        return data.home_temp_source.value
    return "mixed"


_PER_HOUR = "/h"
_ACTION_OPTIONS = [
    "idle",
    "heating",
    "cooling",
    "drying",
    "off",
    "unavailable",
]


@dataclass(frozen=True, kw_only=True)
class SmartClimateSensorDescription(SensorEntityDescription):
    """Describes a home-wide Climate Orchestrator sensor."""

    value_fn: Callable[[SmartClimateCoordinator, SmartClimateData], float | str | None]
    attrs_fn: (
        Callable[[SmartClimateCoordinator, SmartClimateData], dict[str, Any]] | None
    ) = None


def _home_feels_like(
    coord: SmartClimateCoordinator, data: SmartClimateData
) -> float | None:
    """Whole-home comfort index ("feels-like"), scaled by the humidity influence.

    At the default influence of 1.0 this is the full BoM apparent temperature.
    """
    if data.home_avg_temperature is None or data.home_avg_humidity is None:
        return None
    return effective_temperature(
        data.home_avg_temperature,
        data.home_avg_humidity,
        use_comfort=True,
        influence=coord.comfort_influence,
    )


SENSORS: tuple[SmartClimateSensorDescription, ...] = (
    SmartClimateSensorDescription(
        key="home_avg_temperature",
        translation_key="home_avg_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda _coord, data: data.home_avg_temperature,
    ),
    SmartClimateSensorDescription(
        key="home_avg_humidity",
        translation_key="home_avg_humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        value_fn=lambda _coord, data: data.home_avg_humidity,
    ),
    SmartClimateSensorDescription(
        key="home_feels_like_temperature",
        translation_key="home_feels_like_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=_home_feels_like,
    ),
    SmartClimateSensorDescription(
        key="temperature_slope",
        translation_key="temperature_slope",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=_KELVIN_PER_MINUTE,
        suggested_display_precision=3,
        value_fn=lambda coord, _data: coord.temperature_slope,
    ),
    SmartClimateSensorDescription(
        key="adaptive_cool_setpoint",
        translation_key="adaptive_cool_setpoint",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        value_fn=lambda coord, _data: coord.adaptive_band_high,
    ),
    SmartClimateSensorDescription(
        key="status",
        translation_key="status",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=_STATUS_OPTIONS,
        value_fn=lambda _coord, data: data.status.value,
        attrs_fn=lambda _coord, data: {
            "unavailable_devices": sorted(data.unavailable_devices)
        },
    ),
    SmartClimateSensorDescription(
        key="home_avg_source",
        translation_key="home_avg_source",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=_HOME_AVG_SOURCE_OPTIONS,
        value_fn=lambda _coord, data: _home_avg_source(data),
        attrs_fn=lambda coord, data: {
            "temperature_source": data.home_temp_source.value,
            "humidity_source": data.home_humidity_source.value,
            "temperature_sensor": coord.home_temp_sensor,
            "humidity_sensor": coord.home_humidity_sensor,
        },
    ),
    SmartClimateSensorDescription(
        key="running_mean_outdoor_temperature",
        translation_key="running_mean_outdoor_temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda coord, _data: coord.running_mean_outdoor,
    ),
)


def _learning_status(controller: MpcController | None) -> str:
    if controller is None:
        return _LEARNING_IDLE
    if len(controller.history) >= MIN_SAMPLES:
        return _LEARNING_READY
    return _LEARNING_LEARNING


@dataclass(frozen=True, kw_only=True)
class DeviceSensorDescription(SensorEntityDescription):
    """Describes a per-device diagnostic sensor (one per managed device)."""

    value_fn: Callable[[SmartClimateCoordinator, str], float | str | None]
    attrs_fn: Callable[[SmartClimateCoordinator, str], dict[str, Any]] | None = None
    trv_only: bool = False


def _runtime_pct(coord: SmartClimateCoordinator, entity_id: str) -> float | None:
    fraction = coord.device_runtime_fraction(entity_id)
    return None if fraction is None else round(fraction * 100.0, 1)


DEVICE_SENSORS: tuple[DeviceSensorDescription, ...] = (
    DeviceSensorDescription(
        key="device_action",
        translation_key="device_action",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=_ACTION_OPTIONS,
        value_fn=lambda coord, eid: coord.device_action(eid),
        attrs_fn=lambda coord, eid: coord.device_command_attrs(eid),
    ),
    DeviceSensorDescription(
        key="device_runtime",
        translation_key="device_runtime",
        entity_category=EntityCategory.DIAGNOSTIC,
        # Noisy rolling statistics; opt-in (quality scale:
        # entity-disabled-by-default).
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        value_fn=_runtime_pct,
    ),
    DeviceSensorDescription(
        key="device_cycles_per_hour",
        translation_key="device_cycles_per_hour",
        entity_category=EntityCategory.DIAGNOSTIC,
        # Noisy rolling statistics; opt-in (quality scale:
        # entity-disabled-by-default).
        entity_registry_enabled_default=False,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=_PER_HOUR,
        suggested_display_precision=1,
        value_fn=lambda coord, eid: coord.device_cycles_per_hour(eid),
    ),
    DeviceSensorDescription(
        key="valve_position",
        translation_key="valve_position",
        entity_category=EntityCategory.DIAGNOSTIC,
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        suggested_display_precision=0,
        value_fn=lambda coord, eid: coord.valve_position(eid),
        trv_only=True,
    ),
)


def _trv_label(trv_id: str) -> str:
    """Derive a human label for a TRV from its entity_id (``trv_1`` -> ``Trv 1``)."""
    object_id = trv_id.split(".", 1)[-1]
    return object_id.replace("_", " ").title()


async def async_setup_entry(
    _hass: HomeAssistant,
    entry: SmartClimateConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the home-wide sensors and per-TRV MPC diagnostics."""
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [
        SmartClimateSensor(coordinator, description) for description in SENSORS
    ]
    entities.append(SmartClimateReasonSensor(coordinator))
    trvs = set(coordinator.trv_ids)
    entities.extend(
        SmartClimateMpcSensor(coordinator, trv_id, _trv_label(trv_id))
        for trv_id in coordinator.trv_ids
    )
    for entity_id in coordinator.device_ids:
        label = _trv_label(entity_id)
        entities.extend(
            SmartClimateDeviceSensor(coordinator, description, entity_id, label)
            for description in DEVICE_SENSORS
            if not description.trv_only or entity_id in trvs
        )
    async_add_entities(entities)


class SmartClimateSensor(SmartClimateBaseEntity, SensorEntity):
    """A home-wide sensor backed by the coordinator snapshot."""

    entity_description: SmartClimateSensorDescription

    def __init__(
        self,
        coordinator: SmartClimateCoordinator,
        description: SmartClimateSensorDescription,
    ) -> None:
        """Initialise the home-wide sensor."""
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = f"{coordinator.entry.entry_id}_{description.key}"

    @property
    def native_value(self) -> float | str | None:
        """Return the current value."""
        return self.entity_description.value_fn(self.coordinator, self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Optional supporting attributes."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(self.coordinator, self.coordinator.data)


class SmartClimateMpcSensor(SmartClimateBaseEntity, SensorEntity):
    """One MPC diagnostic per TRV: a learning-status enum with the model attached.

    The status is the at-a-glance value; the slow-moving learned numbers
    (heating gain, heat loss, fit RMSE, sample count) ride along as attributes
    rather than as separate MEASUREMENT sensors — they are debugging context,
    not trends worth a recorder series each.
    """

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = _LEARNING_OPTIONS
    _attr_translation_key = "mpc_learning_status"

    def __init__(
        self,
        coordinator: SmartClimateCoordinator,
        trv_id: str,
        label: str,
    ) -> None:
        """Initialise the diagnostic sensor for one TRV."""
        super().__init__(coordinator)
        self._trv_id = trv_id
        self._attr_translation_placeholders = {"trv": label}
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_{trv_id}_mpc_learning_status"
        )

    @property
    def native_value(self) -> str:
        """Return the learning status for this TRV's controller."""
        return _learning_status(self.coordinator.mpc_state(self._trv_id))

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Expose the learned model for this TRV, when one exists."""
        controller = self.coordinator.mpc_state(self._trv_id)
        if controller is None:
            return None
        # Pin params once: the MPC math may re-identify the fit from an executor
        # thread between attribute reads, which would otherwise mix gain from
        # one fit with loss from the next. (fit_rmse already reads a snapshot.)
        params = controller.params
        return {
            "heating_gain": params.gain,  # K/min at 100 % valve
            "heat_loss": params.loss,  # 1/min toward outdoors
            "model_error": controller.fit_rmse(),  # °C RMSE; None until ready
            "samples": len(controller.history),
        }


class SmartClimateDeviceSensor(SmartClimateBaseEntity, SensorEntity):
    """A per-device diagnostic sensor (action, runtime, cycles, valve %)."""

    entity_description: DeviceSensorDescription

    def __init__(
        self,
        coordinator: SmartClimateCoordinator,
        description: DeviceSensorDescription,
        entity_id: str,
        label: str,
    ) -> None:
        """Initialise the diagnostic sensor for one managed device."""
        super().__init__(coordinator)
        self.entity_description = description
        self._device_entity_id = entity_id
        self._attr_translation_placeholders = {"device": label}
        self._attr_unique_id = (
            f"{coordinator.entry.entry_id}_{entity_id}_{description.key}"
        )

    @property
    def native_value(self) -> float | str | None:
        """Return the diagnostic value for this device."""
        return self.entity_description.value_fn(
            self.coordinator, self._device_entity_id
        )

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Optional per-device attributes (e.g. the last command)."""
        if self.entity_description.attrs_fn is None:
            return None
        return self.entity_description.attrs_fn(
            self.coordinator, self._device_entity_id
        )


class SmartClimateReasonSensor(SmartClimateBaseEntity, SensorEntity):
    """Why the whole home is currently heating / cooling / idle."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_translation_key = "hvac_action_reason"
    _attr_options = _REASON_OPTIONS

    def __init__(self, coordinator: SmartClimateCoordinator) -> None:
        """Initialise the reason sensor."""
        super().__init__(coordinator)
        self._attr_unique_id = f"{coordinator.entry.entry_id}_hvac_action_reason"

    @property
    def native_value(self) -> str:
        """The headline reason for the current action."""
        return self.coordinator.hvac_action_reason()

    @property
    def extra_state_attributes(self) -> dict[str, str]:
        """Per-device reasons, for drilling into a whole-home decision."""
        return self.coordinator.device_reasons()
