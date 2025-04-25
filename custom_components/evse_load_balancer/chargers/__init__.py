from .charger import Charger
from .easee_charger import EaseeCharger
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntry
from ..const import CHARGER_DOMAIN_EASEE, SUPPORTED_CHARGER_DEVICE_DOMAINS
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant


async def charger_factory(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry_id: str
) -> Charger:
    """
    Factory function to create a charger instance based on the manufacturer.
    """
    registry = dr.async_get(hass)
    device: DeviceEntry = registry.async_get(device_entry_id)

    if not device:
        raise ValueError(f"Device with ID {device_entry_id} not found in registry.")

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
    else:
        raise ValueError(f"Unsupported manufacturer: {manufacturer}")
