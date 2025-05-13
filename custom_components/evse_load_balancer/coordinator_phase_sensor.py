"""EVSE Load Balancer sensor platform."""

from functools import cached_property

from homeassistant.components.sensor import SensorEntityDescription
from homeassistant.components.sensor.const import UnitOfElectricCurrent
from homeassistant.helpers.entity import (
    EntityCategory,
)

from .const import (
    Phase,
)
from .coordinator import EVSELoadBalancerCoordinator
from .coordinator_sensor import CoordinatorSensor

SENSOR_KEY_AVAILABLE_CURRENT_L1 = "available_current_l1"
SENSOR_KEY_AVAILABLE_CURRENT_L2 = "available_current_l2"
SENSOR_KEY_AVAILABLE_CURRENT_L3 = "available_current_l3"


class CoordinatorPhaseSensor(CoordinatorSensor):
    """Representation of a EVSE Load Balancer sensor."""

    def __init__(
        self,
        coordinator: EVSELoadBalancerCoordinator,
        entity_description: SensorEntityDescription,
    ) -> None:
        """Initialize the CoordinatorPhaseSensor."""
        super().__init__(coordinator=coordinator, entity_description=entity_description)
        self._attr_entity_category = EntityCategory.DIAGNOSTIC
        self._attr_native_unit_of_measurement = UnitOfElectricCurrent.AMPERE

    @property
    def native_value(self) -> int | None:
        """Return the available current from the coordinator."""
        return self._coordinator.get_available_current_for_phase(self._phase)

    @cached_property
    def _phase(self) -> Phase:
        """Return the phase for the sensor."""
        key = self.entity_description.key
        if key in [SENSOR_KEY_AVAILABLE_CURRENT_L1]:
            return Phase.L1
        if key in [SENSOR_KEY_AVAILABLE_CURRENT_L2]:
            return Phase.L2
        if key in [SENSOR_KEY_AVAILABLE_CURRENT_L3]:
            return Phase.L3
        msg = f"No phase for invalid sensor key: {key}"
        raise ValueError(msg)
