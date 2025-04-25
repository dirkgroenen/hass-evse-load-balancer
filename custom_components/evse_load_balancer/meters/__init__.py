"""Meter implemetations."""
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from custom_components.evse_load_balancer.const import (
    METER_DOMAIN_DSMR,
    SUPPORTED_METER_DEVICE_DOMAINS,
)

from .custom_meter import CustomMeter
from .dsmr_meter import DsmrMeter
from .meter import Meter

if TYPE_CHECKING:
    from homeassistant.helpers.device_registry import DeviceEntry

CONST_CUSTOM_METER = "custom_meter"


async def meter_factory(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    custom_config: bool,  # noqa: FBT001
    device_entry_id: str,
) -> Meter:
    """Create a charger instance based on the manufacturer."""
    # custom implementation meter does not come from device
    if custom_config:
        return CustomMeter(hass, config_entry)

    # Grab device from hass
    registry = dr.async_get(hass)
    device: DeviceEntry = registry.async_get(device_entry_id)

    if not device:
        msg = f"Device with ID {device_entry_id} not found in registry."
        raise ValueError(msg)

    manufacturer = next(
        (
            domain
            for [domain, _] in device.identifiers
            if domain in SUPPORTED_METER_DEVICE_DOMAINS
        ),
        None,
    )
    if manufacturer == METER_DOMAIN_DSMR:
        return DsmrMeter(hass, config_entry, device)
    msg = f"Unsupported manufacturer: {manufacturer}"
    raise ValueError(msg)
