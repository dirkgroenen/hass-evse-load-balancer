"""EVSE Load Balancer sensor platform."""

from collections.abc import Callable

from homeassistant import config_entries, core
from homeassistant.components.switch import (
    SwitchDeviceClass,
    SwitchEntity,
    SwitchEntityDescription,
)

from .const import (
    DOMAIN,
)
from .coordinator import EVSELoadBalancerCoordinator
from .coordinator_switch import CoordinatorSwitch
from .utils import get_callable_name


async def async_setup_entry(
    hass: core.HomeAssistant,
    config_entry: config_entries.ConfigEntry,
    async_add_entities: Callable,
) -> None:
    """Set up sensors based on config entry."""
    coordinator: EVSELoadBalancerCoordinator = hass.data[DOMAIN][config_entry.entry_id]

    switches = [
        SwitchClas(coordinator, entity_description)
        for SwitchClas, entity_description in SWITCHES
    ]
    async_add_entities(switches, update_before_add=False)


SWITCHES: tuple[tuple[SwitchEntity, SwitchEntityDescription], ...] = (
    (
        CoordinatorSwitch,
        SwitchEntityDescription(
            key=get_callable_name(EVSELoadBalancerCoordinator.manual_current_override_active),
            name="Current Limit Override",
            device_class=SwitchDeviceClass.SWITCH,
        )
    ),
)
