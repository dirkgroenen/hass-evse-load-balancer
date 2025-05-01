"""Load Balancer Number implementation."""

from homeassistant.components.number import (
    NumberEntity,
)

from .coordinator_entity import CoordinatorEntity


class CoordinatorNumber(CoordinatorEntity, NumberEntity):
    """Setter implementation of a EVSE Load Balancer Number."""

    async def async_set_native_value(self, value: any) -> None:
        """Set new value for the number entity."""
        self._attr_native_value = value
        self._set_value_in_coordinator(value)

    @property
    def native_value(self) -> any:
        """Return the value of the sensor."""
        return self._get_value_in_coordinator()
