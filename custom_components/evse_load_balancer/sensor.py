"""EVSE Load Balancer sensor platform."""

import logging
from collections.abc import Callable

from homeassistant import config_entries, core
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
)

from .const import (
    COORDINATOR_STATES,
    DOMAIN,
)
from .coordinator import EVSELoadBalancerCoordinator
from .load_balancer_phase_sensor import (
    SENSOR_KEY_AVAILABLE_CURRENT_L1,
    SENSOR_KEY_AVAILABLE_CURRENT_L2,
    SENSOR_KEY_AVAILABLE_CURRENT_L3,
    LoadBalancerPhaseSensor,
)
from .load_balancer_sensor import LoadBalancerSensor

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: Callable,
) -> None:
    """Set up sensors based on config entry."""
    coordinator: EVSELoadBalancerCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    sensors = [
        SensorCls(coordinator, entity_description)
        for SensorCls, entity_description in SENSORS
    ]
    async_add_entities(sensors, update_before_add=False)


SENSORS: tuple[tuple[SensorEntity, SensorEntityDescription], ...] = (
    (
        LoadBalancerSensor,
        SensorEntityDescription(
            key=EVSELoadBalancerCoordinator.get_load_balancing_state.__name__,
            name="Load Balancing State",
            options=list(COORDINATOR_STATES),
            device_class=SensorDeviceClass.ENUM,
            entity_registry_enabled_default=True,
        ),
    ),
    (
        LoadBalancerSensor,
        SensorEntityDescription(
            key=EVSELoadBalancerCoordinator.get_last_check_timestamp.__name__,
            name="Last Check",
            device_class=SensorDeviceClass.TIMESTAMP,
            entity_registry_enabled_default=False,
        ),
    ),
    (
        LoadBalancerPhaseSensor,
        SensorEntityDescription(
            key=SENSOR_KEY_AVAILABLE_CURRENT_L1,
            device_class=SensorDeviceClass.CURRENT,
            suggested_display_precision=0,
            entity_registry_enabled_default=False,
        ),
    ),
    (
        LoadBalancerPhaseSensor,
        SensorEntityDescription(
            key=SENSOR_KEY_AVAILABLE_CURRENT_L2,
            device_class=SensorDeviceClass.CURRENT,
            suggested_display_precision=0,
            entity_registry_enabled_default=False,
        ),
    ),
    (
        LoadBalancerPhaseSensor,
        SensorEntityDescription(
            key=SENSOR_KEY_AVAILABLE_CURRENT_L3,
            device_class=SensorDeviceClass.CURRENT,
            suggested_display_precision=0,
            entity_registry_enabled_default=False,
        ),
    ),
)
