from .meter import Meter
from .custom_meter import CustomMeter
from .dsmr_meter import DsmrMeter
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import (
    DeviceEntry
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import (
    device_registry as dr
)
from ..const import (
    SUPPORTED_METER_DEVICE_DOMAINS,
)

CONST_CUSTOM_METER = "custom_meter"


async def meter_factory(hass: HomeAssistant, config_entry: ConfigEntry, custom_config: bool, device_entry_id: str) -> Meter:
    """
    Factory function to create a charger instance based on the manufacturer.
    """
    # custom implementation meter does not come from device
    if custom_config:
        return CustomMeter(hass, config_entry)

    # Grab device from hass
    registry = dr.async_get(hass)
    device: DeviceEntry = registry.async_get(device_entry_id)

    if not device:
        raise ValueError(f"Device with ID {device_entry_id} not found in registry.")

    manufacturer = next((domain for [domain, _] in device.identifiers if domain in SUPPORTED_METER_DEVICE_DOMAINS), None)
    if manufacturer == "dsmr":
        return DsmrMeter(hass, config_entry, device)
    else:
        raise ValueError(f"Unsupported manufacturer: {manufacturer}")
