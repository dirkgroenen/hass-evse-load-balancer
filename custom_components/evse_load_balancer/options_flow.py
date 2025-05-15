"""Config flow for the evse-load-balancer integration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, OptionsFlow, ConfigFlowResult
from homeassistant.helpers.selector import NumberSelector

from .exceptions.validation_exception import ValidationExceptionError 

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

OPTION_CHARGE_LIMIT_HYSTERESIS = "charge_limit_hysteresis"
OPTION_MAX_FUSE_LOAD_AMPS = "max_fuse_load_amps"

DEFAULT_VALUES: dict[str, Any] = {
    OPTION_CHARGE_LIMIT_HYSTERESIS: 15,
    OPTION_MAX_FUSE_LOAD_AMPS: 0, 
}


async def validate_init_input(
    _hass: HomeAssistant, 
    data: dict[str, Any],
) -> dict[str, Any]:
    """Validate the input data for the options flow."""
    return data


class EvseLoadBalancerOptionsFlow(OptionsFlow):
    """Handle an options flow for evse-load-balancer."""

    def __init__(self, config_entry: ConfigEntry | None = None) -> None:
        """Initialize options flow."""
        # This signature allows config_entry to be optional.
        # If HA core calls this with config_entry (e.g. older HA via your config_flow.py),
        # it will be set.
        # If HA core calls this without arguments (e.g. HA >= 2024.11 via your config_flow.py),
        # config_entry will be None here, and HA core will set self.config_entry on the instance.
        if config_entry is not None:
            self.config_entry = config_entry

    @staticmethod
    def get_option_value(config_entry: ConfigEntry, key: str) -> Any:
        """Get the value of an option from the config entry."""
        return config_entry.options.get(key, DEFAULT_VALUES.get(key))

    def _options_schema(self) -> vol.Schema:
        """Define the schema for the options flow."""
        # self.config_entry should be populated by HA before this method is called by a step
        options_values = self.config_entry.options
        
        # Default to 16A if "fuse_size" is not found in config_entry.data
        main_fuse_size_from_config_data = self.config_entry.data.get("fuse_size", 16) 

        return vol.Schema(
            {
                vol.Required(
                    OPTION_CHARGE_LIMIT_HYSTERESIS,
                    default=options_values.get(
                        OPTION_CHARGE_LIMIT_HYSTERESIS,
                        DEFAULT_VALUES.get(OPTION_CHARGE_LIMIT_HYSTERESIS, 15), # Safer default access
                    ),
                ): NumberSelector(
                    {
                        "min": 1,
                        "step": 1,
                        "mode": "box",
                        "unit_of_measurement": "minutes",
                    }
                ),
                vol.Optional(
                    OPTION_MAX_FUSE_LOAD_AMPS,
                    default=options_values.get(
                        OPTION_MAX_FUSE_LOAD_AMPS,
                        DEFAULT_VALUES.get(OPTION_MAX_FUSE_LOAD_AMPS, 0), # Safer default access
                    ),
                ): NumberSelector(
                    {
                        "min": 0, 
                        "max": main_fuse_size_from_config_data, 
                        "step": 1,
                        "mode": "box",
                        "unit_of_measurement": "A",
                    }
                ),
            }
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            processed_input = user_input.copy()
            try:
                if OPTION_MAX_FUSE_LOAD_AMPS in processed_input and processed_input[OPTION_MAX_FUSE_LOAD_AMPS] is not None:
                    processed_input[OPTION_MAX_FUSE_LOAD_AMPS] = int(float(processed_input[OPTION_MAX_FUSE_LOAD_AMPS]))

                input_data = await validate_init_input(self.hass, processed_input) 
            
            except ValidationExceptionError as ex:
                errors[ex.base] = ex.key
            except ValueError: 
                errors["base"] = "invalid_number_format" 
            
            if not errors:
                return self.async_create_entry(title="", data=input_data)

        return self.async_show_form(
            step_id="init", data_schema=self._options_schema(), errors=errors
        )
