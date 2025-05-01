"""Load Balancer Number implementation."""

import logging

from homeassistant.helpers.entity import (
    DeviceInfo,
    Entity,
    EntityDescription,
)

from .const import (
    DOMAIN,
)
from .coordinator import EVSELoadBalancerCoordinator

_LOGGER = logging.getLogger(__name__)


class CoordinatorEntity(Entity):
    """Setter and getter implementation of a EVSE Load Balancer entity."""

    def __init__(
        self,
        coordinator: EVSELoadBalancerCoordinator,
        entity_description: EntityDescription,
    ) -> None:
        """Initialize the base CoordinatorSensor."""
        super().__init__()
        self.entity_description = entity_description
        self._coordinator = coordinator

        self._attr_name = entity_description.name or \
            entity_description.key.replace("_", " ").title()
        self._attr_unique_id = (
            f"{coordinator.config_entry.entry_id}_{entity_description.key}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self._coordinator.config_entry.entry_id)},
            name="EVSE Load Balancer",
            manufacturer="EnergyLabs",
            configuration_url=(
                "https://github.com/dirkgroenen/hass-evse-load-balancer"
            ),
        )
        self._attr_should_poll = False

        self._register_entity()

    def _register_entity(self) -> None:
        """Register the entity with the coordinator."""
        self._coordinator.register_entity(self)

    def _set_value_in_coordinator(self, value: any) -> None:
        setattr(self._coordinator, self.entity_description.key, value)
        self.async_write_ha_state()

    def _get_value_in_coordinator(self) -> any:
        return getattr(self._coordinator, self.entity_description.key, None)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister the sensor from the coordinator."""
        self._coordinator.unregister_entity(self)
