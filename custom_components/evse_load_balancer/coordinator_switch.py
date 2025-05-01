"""Load Balancer Number implementation."""


from homeassistant.components.switch import (
    SwitchEntity,
)

from .coordinator_entity import CoordinatorEntity


class CoordinatorSwitch(CoordinatorEntity, SwitchEntity):
    """Setter implementation of a EVSE Load Balancer Switch."""

    @property
    def is_on(self) -> bool:
        """Return true if the switch is on."""
        return self._get_value_in_coordinator()

    async def async_turn_on(self) -> None:
        """Turn the switch on."""
        self._set_value_in_coordinator(value=True)

    async def async_turn_off(self) -> None:
        """Turn the switch off."""
        self._set_value_in_coordinator(value=False)
