"""EVSE Load Balancer sensor platform."""
import logging

from homeassistant import config_entries, core
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)
from homeassistant.helpers.entity import (
    DeviceInfo,
    EntityCategory,
)
from functools import cached_property
from .coordinator import EVSELoadBalancerCoordinator
from .const import (
    Phase,
    DOMAIN,
)

_LOGGER = logging.getLogger(__name__)

SENSOR_KEY_AVAILABLE_CURRENT_L1 = "available_current_l1"
SENSOR_KEY_AVAILABLE_CURRENT_L2 = "available_current_l2"
SENSOR_KEY_AVAILABLE_CURRENT_L3 = "available_current_l3"

SENSORS: tuple[SensorEntityDescription, ...] = (
    SensorEntityDescription(
        key=SENSOR_KEY_AVAILABLE_CURRENT_L1,
        device_class=SensorDeviceClass.CURRENT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_AVAILABLE_CURRENT_L2,
        device_class=SensorDeviceClass.CURRENT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
    ),
    SensorEntityDescription(
        key=SENSOR_KEY_AVAILABLE_CURRENT_L3,
        device_class=SensorDeviceClass.CURRENT,
        suggested_display_precision=0,
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities,
):
    """Setup sensors from a config entry created in the integrations UI."""
    coordinator: EVSELoadBalancerCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    sensors = [
        LoadBalancerSensor(coordinator, entity_description)
        for entity_description in SENSORS
    ]
    async_add_entities(
        sensors,
        update_before_add=False
    )


class LoadBalancerSensor(SensorEntity):
    """Representation of a EVSE Load Balancer sensor."""

    def __init__(self,
                 coordinator: EVSELoadBalancerCoordinator,
                 entity_description: SensorEntityDescription
                 ):
        super().__init__()
        self.entity_description = entity_description
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._coordinator = coordinator
        self._attr_should_poll = False
        self._attr_name = f"EVSE {entity_description.key.replace('_', ' ').title()}"
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{entity_description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._coordinator.config_entry.entry_id)},
            name="EVSE Load Balancer",
            manufacturer="EnergyLabs",
            configuration_url=(
                "https://energylabs.cloud/xxx"
            ),
        )

        coordinator.register_sensor(self)

    @property
    def native_value(self):
        """Return the current available current from the coordinator."""
        if self.entity_description.device_class == SensorDeviceClass.CURRENT:
            return self._coordinator.get_available_current_for_phase(self._phase)
        else:
            _LOGGER.error(
                f"Cant get sensor value. Sensor {self.entity_description.key} has an invalid device class: {self.entity_description.device_class}."
            )

        return None

    @property
    def available(self) -> bool:
        return self.state is not None

    @cached_property
    def _phase(self) -> Phase:
        """Return the phase for the sensor."""
        key = self.entity_description.key
        if key in [SENSOR_KEY_AVAILABLE_CURRENT_L1]:
            return Phase.L1
        elif key in [SENSOR_KEY_AVAILABLE_CURRENT_L2]:
            return Phase.L2
        elif key in [SENSOR_KEY_AVAILABLE_CURRENT_L3]:
            return Phase.L3
        else:
            raise ValueError(f"No phase for invalid sensor key: {key}")

    def async_will_remove_from_hass(self) -> None:
        """Unregister the sensor from the coordinator."""
        self._coordinator.unregister_sensor(self)
