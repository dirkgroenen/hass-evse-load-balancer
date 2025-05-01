"""Load Balancer sensor platform."""

from .coordinator_entity import CoordinatorEntity


class CoordinatorSensor(CoordinatorEntity):
    """Representation of a EVSE Load Balancer sensor."""

    @property
    def native_value(self) -> any:
        """Return the value of the sensor."""
        return self._get_value_in_coordinator()

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.state is not None
