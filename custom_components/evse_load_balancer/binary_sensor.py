# In /config/custom_components/evse_load_balancer/binary_sensor.py
"""EVSE Load Balancer binary sensor platform."""

import logging
from typing import Callable

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN
from .coordinator import EVSELoadBalancerCoordinator

_LOGGER = logging.getLogger(__name__)

# Define the binary sensor entity class
class EvseBinarySensor(BinarySensorEntity):
    """Representation of an EVSE Load Balancer binary sensor."""

    entity_description: BinarySensorEntityDescription

    def __init__(
        self,
        coordinator: EVSELoadBalancerCoordinator,
        description: BinarySensorEntityDescription,
    ) -> None:
        """Initialize the binary sensor."""
        self.coordinator = coordinator
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{description.key}"
        )
        if coordinator._device: # Check if coordinator._device is available
            self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, coordinator.config_entry.entry_id)},
            )
        else:
             self._attr_device_info = DeviceInfo(
                identifiers={(DOMAIN, coordinator.config_entry.entry_id)}
            )


    @property
    def is_on(self) -> bool | None:
        value = getattr(self.coordinator, self.entity_description.key, None)
        if value is None:
            return None
        return bool(value)

    @property
    def available(self) -> bool:
        return self.coordinator is not None

BINARY_SENSOR_DESCRIPTIONS: tuple[BinarySensorEntityDescription, ...] = (
    BinarySensorEntityDescription(
        key="evse_ev_connected",
        translation_key="evse_ev_connected",
        device_class=BinarySensorDeviceClass.PLUG,
        icon="mdi:power-plug-outline",
        entity_registry_enabled_default=False,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: Callable,
) -> None:
    """Set up binary sensors based on config entry."""
    coordinator: EVSELoadBalancerCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    entities_to_add = [
        EvseBinarySensor(coordinator, description)
        for description in BINARY_SENSOR_DESCRIPTIONS
    ]
    
    _LOGGER.debug(f"Setting up EVSE binary sensors: {entities_to_add}")
    async_add_entities(entities_to_add, update_before_add=False)
