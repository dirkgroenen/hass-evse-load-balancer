"""Base Charger Class."""

from abc import ABC, abstractmethod
from enum import Enum

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from ..const import Phase  # noqa: TID252


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

    @property
    def id(self) -> str:
        """Return the unique ID of the charger."""
        return self.config_entry.entry_id

    @abstractmethod
    def set_phase_mode(self, mode: PhaseMode, phase: Phase) -> None:
        """Set the phase mode of the charger."""

    @abstractmethod
    def has_synced_phase_limits(self) -> bool:
        """
        Return whether the charger has synced phase limits.

        This means that the charger is able to set the current limit for each
        phase independently.
        """

    @abstractmethod
    async def set_current_limit(self, limit: dict[Phase, int]) -> None:
        """Set the charger limit in amps."""

    @abstractmethod
    def get_current_limit(self) -> dict[Phase, int] | None:
        """
        Get the current limit of the charger in amps.

        This should return the current limit for each phase.
        """

    @abstractmethod
    def get_max_current_limit(self) -> dict[Phase, int] | None:
        """Get the configured maximum current limit of the charger in amps."""

    @abstractmethod
    def car_connected(self) -> bool:
        """
        Return whether the car is connected to the charger and ready to receive charge.

        This does not mean that the car is actually able to charge, for which
        you can use can_charge().

        When the connected car is not authorised (and therefore the charger is not
        ready) we consider it a "disconnected" state.
        """

    @abstractmethod
    def can_charge(self) -> bool:
        """Return whether the car is connected and charging or accepting charge."""
