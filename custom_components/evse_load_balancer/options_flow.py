"""Config flow for the evse-load-balancer integration."""

from __future__ import annotations

import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import OptionsFlow, ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.selector import (
    NumberSelector
)
from .exceptions.validation_exception import ValidationException

_LOGGER = logging.getLogger(__name__)

OPTION_CHARGE_LIMIT_HYSTERESIS = "charge_limit_hysteresis"

DEFAULT_VALUES: dict[str, Any] = {
    OPTION_CHARGE_LIMIT_HYSTERESIS: 5
}


async def validate_init_input(hass: HomeAssistant, data: dict[str, Any]) -> dict[str, Any]:
    return data


class EvseLoadBalancerOptionsFlow(OptionsFlow):
    """Handle an options flow for evse-load-balancer."""

    @staticmethod
    def get_option_value(config_entry: ConfigEntry, key: str) -> Any:
        return config_entry.options.get(key, DEFAULT_VALUES[key])

    def _options_schema(self) -> vol.Schema:
        options_values = self.config_entry.options
        return vol.Schema(
            {
                vol.Required(
                    OPTION_CHARGE_LIMIT_HYSTERESIS,
                    default=options_values.get(OPTION_CHARGE_LIMIT_HYSTERESIS, DEFAULT_VALUES[OPTION_CHARGE_LIMIT_HYSTERESIS])
                ): NumberSelector({"min": 1, "step": 1, "mode": "box", "unit_of_measurement": "minutes"}),
            }
        )

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> dict[str, any]:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                input_data = await validate_init_input(self.hass, user_input)
            except ValidationException as ex:
                errors[ex.base] = ex.key
            if not errors:
                return self.async_create_entry(
                    title="",
                    data=input_data
                )

        return self.async_show_form(
            step_id="init",
            data_schema=self._options_schema(),
            errors=errors
        )
