from abc import ABC, abstractmethod
from homeassistant.core import HomeAssistant
from ..const import Phase
from typing import Optional
from homeassistant.config_entries import ConfigEntry


class Meter(ABC):
    """
    Base class for all energy meter.
    """

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry):
        """
        Initialize the Meter instance.
        """
        self.hass = hass
        self.config_entry = config_entry

    @abstractmethod
    def get_active_phase_current(self, phase: Phase) -> Optional[int]:
        """
        Returns the available current on a given phase
        """
        pass

    @abstractmethod
    def get_active_phase_power(self, phase: Phase) -> Optional[float]:
        """
        Returns the active power on a given phase
        """
        pass

    @abstractmethod
    def get_tracking_entities(self) -> list[str]:
        """
        Returns a list of entity IDs that should be tracked for this meter
        to function properly.
        """
        pass
