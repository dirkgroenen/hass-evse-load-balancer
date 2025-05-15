"""EVSE Load Balancer Chargers."""

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from ..const import (   # noqa: TID252
    CHARGER_DOMAIN_EASEE,
    SUPPORTED_CHARGER_DEVICE_DOMAINS,
    HA_INTEGRATION_DOMAIN_MQTT,
    MANUFACTURER_AMINA,
)
from .charger import Charger
from .easee_charger import EaseeCharger
from .amina_charger import AminaCharger

if TYPE_CHECKING:
    from homeassistant.helpers.device_registry import DeviceEntry

_LOGGER = logging.getLogger(__name__)


async def charger_factory(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry_id: str
) -> Charger:
    """Create a charger instance based on the device's properties."""
    registry = dr.async_get(hass)
    device: DeviceEntry | None = registry.async_get(device_entry_id)

    if not device:
        msg = f"Device with ID {device_entry_id} not found in registry."
        _LOGGER.error(msg)
        raise ValueError(msg)

    # Log device details for debugging purposes
    _LOGGER.debug(
        f"Charger Factory attempting to create charger for device: "
        f"Name='{device.name}', Manufacturer='{device.manufacturer}', Model='{device.model}', "
        f"Identifiers='{device.identifiers}'"
    )

    # Check for Easee chargers
    if any(id_domain == CHARGER_DOMAIN_EASEE for id_domain, _ in device.identifiers):
        _LOGGER.info(f"Creating EaseeCharger for device {device.name}")
        return EaseeCharger(hass, config_entry, device)

    # Check for Amina chargers
    is_amina_device_via_mqtt_properties = False
    for id_domain, id_value in device.identifiers:
        if (id_domain == HA_INTEGRATION_DOMAIN_MQTT and
            id_value.startswith("zigbee2mqtt_") and
            device.manufacturer == MANUFACTURER_AMINA):
            is_amina_device_via_mqtt_properties = True
            break
            
    if is_amina_device_via_mqtt_properties:
        _LOGGER.info(
            f"Creating AminaCharger for device {device.name} "
            f"(Identified as MQTT device, Z2M-like ID value, Manufacturer: {MANUFACTURER_AMINA})"
        )
        return AminaCharger(hass, config_entry, device)
    else:
        if device.manufacturer == MANUFACTURER_AMINA:
            _LOGGER.debug(
                f"Device {device.name} is from Manufacturer '{MANUFACTURER_AMINA}' but "
                f"identifier pattern did not match expected Z2M via MQTT. "
                f"Identifiers: {device.identifiers}"
            )

    error_details = (
        f"Identifiers: {device.identifiers}, Manufacturer: {device.manufacturer}, Model: {device.model}"
    )
    _LOGGER.error(
        f"Unsupported charger: No specific charger class matched in factory for device '{device.name}'. "
        f"Details: {error_details}"
    )
    raise ValueError(
        f"Unsupported charger type for device '{device.name}'. Details: {error_details}"
    )