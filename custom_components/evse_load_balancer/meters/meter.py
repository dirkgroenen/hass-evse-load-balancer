from abc import ABC, abstractmethod
from homeassistant.core import HomeAssistant
from ..const import Phase
from typing import Optional


class Meter(ABC):
    """
    Base class for all energy meter.
    """

    def __init__(
        self,
        hass: HomeAssistant,
    ):
        """
        Initialize the Meter instance.
        """
        self.hass = hass

    @abstractmethod
    def get_active_phase_current(self, phase: Phase) -> Optional[float]:
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

    @abstractmethod
    def refresh_entities(self) -> None:
        """
        Refreshes the entities for the meter.
        """
    pass
