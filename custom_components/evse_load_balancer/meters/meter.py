"""Meter implementations."""
from abc import ABC, abstractmethod

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from ..const import Phase


class Meter(ABC):
    """Base class for all energy meter."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the Meter instance."""
        self.hass = hass
        self.config_entry = config_entry

    @abstractmethod
    def get_active_phase_current(self, phase: Phase) -> int | None:
        """Return the available current on a given phase."""

    @abstractmethod
    def get_active_phase_power(self, phase: Phase) -> float | None:
        """Return the active power on a given phase."""

    @abstractmethod
    def get_tracking_entities(self) -> list[str]:
        """Return a list of entity IDs that should be tracked for the meter."""
