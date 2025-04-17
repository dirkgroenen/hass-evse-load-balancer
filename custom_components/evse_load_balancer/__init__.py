"""EVSE Load Balancer Integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform

from .chargers import (charger_factory, Charger)
from .meters import (meter_factory, Meter)
from homeassistant.core import HomeAssistant
from . import config_flow as cf
from .const import DOMAIN
from .coordinator import EVSELoadBalancerCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the EVSE Load Balancer integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EVSE Load Balancer from a config entry."""

    meter: Meter = await meter_factory(hass, entry, entry.data.get(cf.CONF_CUSTOM_PHASE_CONFIG, False), entry.data.get(cf.CONF_METER_DEVICE))
    charger: Charger = await charger_factory(hass, entry, entry.data.get(cf.CONF_CHARGER_DEVICE))

    coordinator = EVSELoadBalancerCoordinator(
        hass=hass,
        config_entry=entry,
        meter=meter,
        charger=charger,
    )
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await coordinator.async_setup()

    _LOGGER.info("EVSE Load Balancer initialized for %s", entry.entry_id)

    hass.async_create_task(
        hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: EVSELoadBalancerCoordinator = hass.data[DOMAIN][entry.entry_id]
    await coordinator.async_unload()
    hass.data[DOMAIN].pop(entry.entry_id, None)
    return True
