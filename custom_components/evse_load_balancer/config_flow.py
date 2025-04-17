"""Config flow for the evse-load-balancer integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.core import callback
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.core import HomeAssistant
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.selector import (
    EntitySelector,
    EntitySelectorConfig,
    DeviceSelector,
    NumberSelector,
    DeviceSelectorConfig,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
)
from homeassistant.data_entry_flow import section

from .options_flow import EvseLoadBalancerOptionsFlow

from .exceptions.validation_exception import ValidationException

from .const import DOMAIN, SUPPORTED_METER_DEVICE_DOMAINS, SUPPORTED_CHARGER_DEVICE_DOMAINS

_LOGGER = logging.getLogger(__name__)

CONF_FUSE_SIZE = "fuse_size"
CONF_PHASE_COUNT = "phase_count"
CONF_PHASE_KEY_ONE = "l1"
CONF_PHASE_KEY_TWO = "l2"
CONF_PHASE_KEY_THREE = "l3"
CONF_PHASE_SENSOR_CONSUMPTION = "power_consumption"
CONF_PHASE_SENSOR_PRODUCTION = "power_production"
CONF_PHASE_SENSOR_VOLTAGE = "voltage"
CONF_CUSTOM_PHASE_CONFIG = "custom_phase_config"
CONF_METER_DEVICE = "meter_device"
CONF_CHARGER_DEVICE = "charger_device"

STEP_INIT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CHARGER_DEVICE): DeviceSelector(
            DeviceSelectorConfig(
                multiple=False,
                filter=[{
                    "integration": domain
                } for domain in SUPPORTED_CHARGER_DEVICE_DOMAINS],
            )
        ),
        vol.Required(CONF_FUSE_SIZE): NumberSelector({"min": 1, "mode": "box", "unit_of_measurement": "A"}),
        vol.Required(CONF_PHASE_COUNT): NumberSelector({"min": 1, "max": 3, "mode": "box"}),
        vol.Optional(CONF_METER_DEVICE): DeviceSelector(
            DeviceSelectorConfig(
                multiple=False,
                filter=[{
                    "integration": domain
                } for domain in SUPPORTED_METER_DEVICE_DOMAINS],
            )
        ),
        vol.Optional(CONF_CUSTOM_PHASE_CONFIG): cv.boolean,
    }
)

STEP_POWER_DATA_SCHEMA = {}


async def validate_init_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    if not data.get(CONF_METER_DEVICE) and not data.get(CONF_CUSTOM_PHASE_CONFIG):
        # If the user has selected a custom phase configuration, but not a meter device,
        # we need to show an error message.
        raise ValidationException("base", "metering_selection_required")

    return data


async def validate_power_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    # Return info that you want to store in the config entry.
    return data


def create_phase_power_data_schema(phase_count: int) -> vol.Schema:
    """Create a schema for the power collection step based on the phase count."""
    extra_schema = {}

    # Limit through kets of CONF_PHASE_SENSORS and limit by phase_count
    for PHASE_KEY in [CONF_PHASE_KEY_ONE, CONF_PHASE_KEY_TWO, CONF_PHASE_KEY_THREE][:int(phase_count)]:
        # Create a section for each phase
        extra_schema[vol.Required(PHASE_KEY)] = section(
            vol.Schema(
                {
                    vol.Required(CONF_PHASE_SENSOR_CONSUMPTION): EntitySelector(
                        EntitySelectorConfig(
                            multiple=False, domain="sensor", device_class=[SensorDeviceClass.POWER]
                        )
                    ),
                    vol.Required(CONF_PHASE_SENSOR_PRODUCTION): EntitySelector(
                        EntitySelectorConfig(
                            multiple=False, domain="sensor", device_class=[SensorDeviceClass.POWER]
                        )
                    ),
                    vol.Required(CONF_PHASE_SENSOR_VOLTAGE): EntitySelector(
                        EntitySelectorConfig(
                            multiple=False, domain="sensor", device_class=[SensorDeviceClass.VOLTAGE]
                        )
                    )
                }
            ),
            # Whether or not the section is initially collapsed (default = False)
            {"collapsed": False},
        )

    return vol.Schema(STEP_POWER_DATA_SCHEMA | extra_schema)


class EvseLoadBalancerConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for evse-load-balancer."""

    VERSION = 1
    MINOR_VERSION = 1

    data = {}

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Get the options flow for this handler."""
        return EvseLoadBalancerOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                input_data = await validate_init_input(self.hass, user_input)
            except ValidationException as ex:
                errors[ex.base] = ex.key
            if not errors:
                self.data = input_data
                if self.data.get(CONF_CUSTOM_PHASE_CONFIG, False):
                    return await self.async_step_power()
                else:
                    return self.async_create_entry(
                        title="EVSE Load Balancer",
                        data=self.data,
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_INIT_SCHEMA,
            errors=errors
        )

    async def async_step_power(
            self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """ Handle the power collection step """
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                input_data = await validate_power_input(self.hass, user_input)
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            if not errors:
                self.data = self.data | input_data
                return self.async_create_entry(
                    title="EVSE Load Balancer",
                    data=self.data,
                )

        return self.async_show_form(
            step_id="power",
            data_schema=create_phase_power_data_schema(
                phase_count=self.data.get(CONF_PHASE_COUNT, 1)
            ),
            errors=errors
        )
