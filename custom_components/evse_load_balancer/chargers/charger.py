"""Base Charger Class."""

from abc import ABC, abstractmethod
from enum import Enum

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from custom_components.evse_load_balancer.const import Phase


class PhaseMode(Enum):
    """Enum to represent the phase mode of the charger."""

    SINGLE = "single"
    MULTI = "multi"


class Charger(ABC):
    """Base class for all chargers."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        device: DeviceEntry,
    ) -> None:
        """Initialize the Charger instance."""
        self.hass = hass
        self.config_entry = config_entry
        self.device = device

    @abstractmethod
    def set_phase_mode(self, mode: PhaseMode, phase: Phase) -> None:
        """Set the phase mode of the charger."""

    @abstractmethod
    async def set_current_limit(self, limit: dict[Phase, int]) -> None:
        """Set the charger limit in amps."""

    @abstractmethod
    def get_current_limit(self) -> dict[Phase, int]:
        """
        Get the current limit of the charger in amps.

        This should return the current limit for each phase.
        If the charger does not support this, return None for all phases.
        """

    @abstractmethod
    def car_connected(self) -> bool:
        """
        Return whether the car is connected to the charger and ready to receive charge.

        This does not mean that the car is
        actually charging. Combine with is_charging() to determine if the car
        is already charging.

        When the connected car is not authorised (and therefore the charger is not
        ready) we consider it a "disconnected" state.
        """

    @abstractmethod
    def is_charging(self) -> bool:
        """Return whether we are charging the car."""
