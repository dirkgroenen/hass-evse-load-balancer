"""Config flow for the evse-load-balancer integration."""

from __future__ import annotations

import logging
from typing import Any

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.components.sensor import (
    SensorDeviceClass,
)
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult
from homeassistant.const import __version__ as ha_version
from homeassistant.core import HomeAssistant, callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers.selector import (
    DeviceSelector,
    DeviceSelectorConfig,
    EntitySelector,
    EntitySelectorConfig,
    NumberSelector,
)
from packaging.version import parse as parse_version

from .const import (
    DOMAIN,
    SUPPORTED_CHARGER_DEVICE_DOMAINS,
    SUPPORTED_METER_DEVICE_DOMAINS,
    CHARGER_DOMAIN_EASEE,
    CHARGER_DOMAIN_ZAPTEC,
    HA_INTEGRATION_DOMAIN_MQTT,
    MANUFACTURER_AMINA,
    MODEL_AMINA_S_OFFICIAL_NAME,
    MODEL_AMINA_S_Z2M_INTERNAL,
)
from .exceptions.validation_exception import ValidationExceptionError
from .options_flow import EvseLoadBalancerOptionsFlow

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

# --- Construct the specific filter list for charger devices ---
_charger_device_filter_list: list[dict[str, str]] = []

if CHARGER_DOMAIN_EASEE in SUPPORTED_CHARGER_DEVICE_DOMAINS:
    _charger_device_filter_list.append({"integration": CHARGER_DOMAIN_EASEE})

if CHARGER_DOMAIN_ZAPTEC in SUPPORTED_CHARGER_DEVICE_DOMAINS:
    _charger_device_filter_list.append({"integration": CHARGER_DOMAIN_ZAPTEC})

if HA_INTEGRATION_DOMAIN_MQTT in SUPPORTED_CHARGER_DEVICE_DOMAINS:
    _charger_device_filter_list.append(
        {
            "integration": HA_INTEGRATION_DOMAIN_MQTT,
            "manufacturer": MANUFACTURER_AMINA,
            "model": MODEL_AMINA_S_OFFICIAL_NAME
        }
    )
    # Add a second filter if the internal Z2M model name is different and might be used
    if MODEL_AMINA_S_OFFICIAL_NAME != MODEL_AMINA_S_Z2M_INTERNAL:
        _charger_device_filter_list.append(
            {
                "integration": HA_INTEGRATION_DOMAIN_MQTT,
                "manufacturer": MANUFACTURER_AMINA,
                "model": MODEL_AMINA_S_Z2M_INTERNAL
            }
        )
# --- End of filter list construction ---

STEP_INIT_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CHARGER_DEVICE): DeviceSelector(
            DeviceSelectorConfig(
                multiple=False,
                filter=_charger_device_filter_list, # MODIFIED: Use the new specific filter list
            )
        ),
        vol.Required(CONF_FUSE_SIZE): NumberSelector(
            {"min": 1, "mode": "box", "unit_of_measurement": "A"}
        ),
        vol.Required(CONF_PHASE_COUNT): NumberSelector(
            {"min": 1, "max": 3, "mode": "box"}
        ),
        vol.Optional(CONF_METER_DEVICE): DeviceSelector(
            DeviceSelectorConfig(
                multiple=False,
                filter=[
                    {"integration": domain} for domain in SUPPORTED_METER_DEVICE_DOMAINS
                ],
            )
        ),
        vol.Optional(CONF_CUSTOM_PHASE_CONFIG): cv.boolean,
    }
)

STEP_POWER_DATA_SCHEMA = {}


async def validate_init_input(
    _hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the user input for the initial step."""
    if not data.get(CONF_METER_DEVICE) and not data.get(CONF_CUSTOM_PHASE_CONFIG):
        # If the user has selected a custom phase configuration, but not a meter device,
        # we need to show an error message.
        raise ValidationExceptionError("base", "metering_selection_required")  # noqa: EM101

    return data


async def validate_power_input(
    _hass: HomeAssistant, data: dict[str, Any]
) -> dict[str, Any]:
    """Validate the user input for the power collection step."""
    # Return info that you want to store in the config entry.
    return data


def create_phase_power_data_schema(phase_count: int) -> vol.Schema:
    """Create a schema for the power collection step based on the phase count."""
    extra_schema = {}

    # Limit through each of CONF_PHASE_SENSORS and limit by phase_count
    for phase_key in [CONF_PHASE_KEY_ONE, CONF_PHASE_KEY_TWO, CONF_PHASE_KEY_THREE][
        : int(phase_count)
    ]:
        # Create a section for each phase
        extra_schema[vol.Required(phase_key)] = section(
            vol.Schema(
                {
                    vol.Required(CONF_PHASE_SENSOR_CONSUMPTION): EntitySelector(
                        EntitySelectorConfig(
                            multiple=False,
                            domain="sensor",
                            device_class=[SensorDeviceClass.POWER],
                        )
                    ),
                    vol.Required(CONF_PHASE_SENSOR_PRODUCTION): EntitySelector(
                        EntitySelectorConfig(
                            multiple=False,
                            domain="sensor",
                            device_class=[SensorDeviceClass.POWER],
                        )
                    ),
                    vol.Required(CONF_PHASE_SENSOR_VOLTAGE): EntitySelector(
                        EntitySelectorConfig(
                            multiple=False,
                            domain="sensor",
                            device_class=[SensorDeviceClass.VOLTAGE],
                        )
                    ),
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

    data = {}  # noqa: RUF012

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: ConfigEntry,
    ) -> EvseLoadBalancerOptionsFlow:
        """Get the options flow for this handler."""
        # see https://developers.home-assistant.io/blog/2024/11/12/options-flow/
        if parse_version(ha_version) < parse_version("2024.11.0"):
            return EvseLoadBalancerOptionsFlow(config_entry=config_entry)

        return EvseLoadBalancerOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                input_data = await validate_init_input(self.hass, user_input)
            except ValidationExceptionError as ex:
                errors[ex.base] = ex.key
            if not errors:
                self.data.update(input_data) # Changed to update for multi-step data accumulation
                if self.data.get(CONF_CUSTOM_PHASE_CONFIG, False):
                    return await self.async_step_power()
                return self.async_create_entry(
                    title="EVSE Load Balancer",
                    data=self.data,
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_INIT_SCHEMA, errors=errors
        )

    async def async_step_power(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the power collection step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                input_data = await validate_power_input(self.hass, user_input)
            except Exception:
                _LOGGER.exception("Unexpected exception")
                errors["base"] = "unknown"
            if not errors:
                self.data.update(input_data) # Merge with existing data
                return self.async_create_entry(
                    title="EVSE Load Balancer",
                    data=self.data,
                )

        return self.async_show_form(
            step_id="power",
            data_schema=create_phase_power_data_schema(
                phase_count=self.data.get(CONF_PHASE_COUNT, 1)
            ),
            errors=errors,
        )
