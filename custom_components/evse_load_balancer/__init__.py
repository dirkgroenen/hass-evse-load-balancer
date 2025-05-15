"""EVSE Load Balancer Integration."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv

from . import config_flow as cf
from .chargers import Charger, charger_factory
from .const import DOMAIN
from .coordinator import EVSELoadBalancerCoordinator
from .meters import Meter, meter_factory

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:  # noqa: ARG001
    """Set up the EVSE Load Balancer integration."""
    hass.data.setdefault(DOMAIN, {})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up EVSE Load Balancer from a config entry."""
    meter: Meter = await meter_factory(
        hass,
        entry,
        entry.data.get(cf.CONF_CUSTOM_PHASE_CONFIG, False),
        entry.data.get(cf.CONF_METER_DEVICE),
    )
    charger: Charger = await charger_factory(
        hass, entry, entry.data.get(cf.CONF_CHARGER_DEVICE)
    )

    # --- SECTION for MQTT charger setup ---
    # Check if the instantiated charger has an async_setup_mqtt method
    if hasattr(charger, "async_setup_mqtt") and callable(
        getattr(charger, "async_setup_mqtt")
    ):
        _LOGGER.info(
            f"Charger '{charger.__class__.__name__}' has async_setup_mqtt, calling it."
        )
        try:
            await charger.async_setup_mqtt()
        except Exception as e:
            _LOGGER.error(
                f"Error during async_setup_mqtt for charger {charger.__class__.__name__}: {e}"
            )
            # Depending on severity, you might want to return False here to indicate setup failure
            # For now, we'll let it proceed to coordinator setup but log the error.
            # If MQTT setup is critical, return False:
            # return False 
    # --- END MQTT SECTION ---

    _LOGGER.info(
        "Setting up entry with meter '%s' and charger '%s'",
        meter.__class__.__name__,
        charger.__class__.__name__,
    )

    coordinator = EVSELoadBalancerCoordinator(
        hass=hass,
        config_entry=entry,
        meter=meter,
        charger=charger,
    )
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await coordinator.async_setup()

    _LOGGER.debug("EVSE Load Balancer initialized for %s", entry.entry_id)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: EVSELoadBalancerCoordinator = hass.data[DOMAIN].get(entry.entry_id)
    
    if coordinator:
        charger_instance = coordinator._charger

        # --- SECTION for MQTT based charger unload ---
        # Check if the charger instance has an async_unload_mqtt method
        if hasattr(charger_instance, "async_unload_mqtt") and callable(
            getattr(charger_instance, "async_unload_mqtt")
        ):
            _LOGGER.info(
                f"Charger '{charger_instance.__class__.__name__}' has async_unload_mqtt, calling it."
            )
            try:
                await charger_instance.async_unload_mqtt()
            except Exception as e:
                _LOGGER.error(
                    f"Error during async_unload_mqtt for charger {charger_instance.__class__.__name__}: {e}"
                )
        # --- END MQTT SECTION ---

        await coordinator.async_unload() # Call coordinator's own unload method

    # Unload platforms
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    
    if unloaded and coordinator: # Ensure coordinator was found before trying to pop
        hass.data[DOMAIN].pop(entry.entry_id, None)
        
    return unloaded # Return the result of unloading platforms