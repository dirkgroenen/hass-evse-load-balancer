from abc import ABC, abstractmethod
from enum import Enum
from typing import Optional
from homeassistant.helpers.device_registry import (
    DeviceEntry,
)
from homeassistant.core import HomeAssistant


class PhaseMode(Enum):
    """
    Enum to represent the phase mode of the charger.
    """
    SINGLE = "single"
    MULTI = "multi"


class Charger(ABC):
    """
    Base class for all chargers. Defines the required interface for all charger implementations.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device: DeviceEntry,
    ):
        """
        Initialize the Charger instance.
        """
        self.hass = hass
        self.device = device

    @abstractmethod
    def set_phase_mode(self, mode: PhaseMode, phase: int):
        """
        Set the phase mode of the charger.
        """
        pass

    @abstractmethod
    def set_current_limit(self, limit: int):
        """
        Set the charger limit in amps.
        """
        pass

    @abstractmethod
    def get_current_limit(self) -> Optional[int]:
        """
        Set the charger limit in amps.
        """
        pass
