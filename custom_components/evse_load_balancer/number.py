"""EVSE Load Balancer sensor platform."""

from collections.abc import Callable

from homeassistant import config_entries, core
from homeassistant.components.number import (
    NumberEntity,
    NumberEntityDescription,
)
from homeassistant.components.number.const import (
    NumberDeviceClass,
    NumberMode,
    UnitOfElectricCurrent,
)

from .const import (
    DOMAIN,
)
from .coordinator import EVSELoadBalancerCoordinator
from .coordinator_number import CoordinatorNumber
from .utils import get_callable_name


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: Callable,
) -> None:
    """Set up sensors based on config entry."""
    coordinator: EVSELoadBalancerCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    numbers = [
        NumberCls(coordinator, entity_description)
        for NumberCls, entity_description in NUMBERS
    ]
    async_add_entities(numbers, update_before_add=False)


NUMBERS: tuple[tuple[NumberEntity, NumberEntityDescription], ...] = (
    (
        CoordinatorNumber,
        NumberEntityDescription(
            key=get_callable_name(EVSELoadBalancerCoordinator.manual_current_limit),
            name="Current Limit",
            native_step=1,
            native_min_value=0,
            native_max_value=80,
            entity_registry_enabled_default=True,
            mode=NumberMode.BOX,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            device_class=NumberDeviceClass.CURRENT,
        )
    ),
)
