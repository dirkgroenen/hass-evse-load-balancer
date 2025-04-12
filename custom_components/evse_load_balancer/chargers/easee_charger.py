from typing import Optional
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import (
    DeviceEntry,
)
from .charger import (Charger, PhaseMode)
from ..const import CHARGER_DOMAIN_EASEE


class EaseeCharger(Charger):
    """
    Implementation of the Charger class for Easee chargers.
    """

    def __init__(self, hass: HomeAssistant, device: DeviceEntry):
        self.hass = hass
        self.device = device
        self._current_limit_mock = 16

    def set_phase_mode(self, mode: PhaseMode, phase: int):
        if mode not in PhaseMode:
            raise ValueError("Invalid mode. Must be 'single' or 'multi'.")
        # Implement the logic to set the phase mode for Easee chargers

    def set_current_limit(self, limit: int):
        if limit <= 0:
            raise ValueError("Limit must be a positive integer.")
        self._current_limit_mock = limit

    def get_current_limit(self) -> Optional[int]:
        # Implement the logic to get the current limit for Easee chargers
        return self._current_limit_mock
