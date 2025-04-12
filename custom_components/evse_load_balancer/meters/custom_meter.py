from typing import Optional
from homeassistant.helpers import entity_registry as er
from homeassistant.core import HomeAssistant
from .meter import (Meter, Phase)


class CustomMeter(Meter):
    """
    Customer Meter implementation of the Meter class.
    """

    def __init__(
        self,
        hass: HomeAssistant,
    ):
        """
        Initialize the Meter instance.
        """
        self.hass = hass

    def get_active_phase_current(self, phase: Phase) -> Optional[float]:
        """
        Returns the available current on a given phase
        """
        return None

    def get_active_phase_power(self, phase: Phase) -> Optional[float]:
        """
        Returns the active power on a given phase
        """
        return None

    def get_tracking_entities(self) -> list[str]:
        """
        Returns a list of entity IDs that should be tracked for this meter
        to function properly. 
        """
        return []

    def refresh_entities(self) -> None:
        """
        Refreshes the entities for the meter.
        """
        pass
