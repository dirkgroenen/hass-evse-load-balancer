"""EVSE Load Balancer Chargers."""
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.evse_load_balancer.const import (
    CHARGER_DOMAIN_EASEE,
    SUPPORTED_CHARGER_DEVICE_DOMAINS,
)

from .charger import Charger
from .easee_charger import EaseeCharger

if TYPE_CHECKING:
    from homeassistant.helpers.device_registry import DeviceEntry


async def charger_factory(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry_id: str
) -> Charger:
    """Create a charger instance based on the manufacturer."""
    registry = dr.async_get(hass)
    device: DeviceEntry = registry.async_get(device_entry_id)

    if not device:
        msg = f"Device with ID {device_entry_id} not found in registry."
        raise ValueError(msg)

    manufacturer = next(
        (
            domain
            for [domain, _] in device.identifiers
            if domain in SUPPORTED_CHARGER_DEVICE_DOMAINS
        ),
        None,
    )
    if manufacturer == CHARGER_DOMAIN_EASEE:
        return EaseeCharger(hass, config_entry, device)
    msg = f"Unsupported manufacturer: {manufacturer}"
    raise ValueError(msg)
