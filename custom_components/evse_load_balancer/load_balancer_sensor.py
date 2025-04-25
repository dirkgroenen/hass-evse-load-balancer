"""Load Balancer sensor platform."""

import logging

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.helpers.entity import (
    DeviceInfo,
)

from .const import (
    DOMAIN,
)
from .coordinator import EVSELoadBalancerCoordinator

_LOGGER = logging.getLogger(__name__)


class LoadBalancerSensor(SensorEntity):
    """Representation of a EVSE Load Balancer sensor."""

    def __init__(
        self,
        coordinator: EVSELoadBalancerCoordinator,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the LoadBalancerSensor."""
        super().__init__()
        self.entity_description = entity_description
        self._coordinator = coordinator
        self._attr_should_poll = False
        self._attr_name = entity_description.key.replace("_", " ").title()
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{entity_description.key}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._coordinator.config_entry.entry_id)},
            name="EVSE Load Balancer",
            manufacturer="EnergyLabs",
            configuration_url=("https://energylabs.cloud/xxx"),
        )

        coordinator.register_sensor(self)

    @property
    def native_value(self) -> any:
        """Return the value of the sensor."""
        return self._get_value_from_coordinator()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.state is not None

    def _get_value_from_coordinator(self) -> any:
        """Override in subclass or implement coordinator lookup based on key."""
        return getattr(self._coordinator, self.entity_description.key, None)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister the sensor from the coordinator."""
        self._coordinator.unregister_sensor(self)
