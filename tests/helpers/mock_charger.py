"""Test helpers for EVSE Load Balancer."""

from typing import Dict, Optional

from custom_components.evse_load_balancer.chargers.charger import Charger, PhaseMode
from custom_components.evse_load_balancer.const import Phase


class MockCharger(Charger):
    """Mock implementation of a Charger for testing."""

    def __init__(self,
                 initial_current: int = 10,
                 max_current: int = 16,
                 synced_phases: bool = True,
                 charger_id: str = "mock_id",
                 device_id: str = "mock_device_id") -> None:
        """Initialize MockCharger with configurable parameters."""
        # Skip the parent class initialization to avoid needing HomeAssistant, etc.
        # This is safe for testing but wouldn't work in production
        self.hass = None
        self.config_entry = type('ConfigEntry', (), {'entry_id': charger_id})()
        self.device = type('DeviceEntry', (), {'id': device_id})()

        # Charger state
        self._current_limit = {phase: initial_current for phase in Phase}
        self._max_current_limit = {phase: max_current for phase in Phase}
        self._synced_phases = synced_phases
        self._is_car_connected = False
        self._can_charge_state = False
        self._is_charging = False

    def is_charger_device(self, device) -> bool:
        """Check if the given device is a mock charger."""
        return any(id_domain == "mock" for id_domain, _ in device.identifiers)

    def set_phase_mode(self, mode: PhaseMode, phase: Phase) -> None:
        """Set the phase mode of the charger."""
        pass  # Not needed for current tests

    def has_synced_phase_limits(self) -> bool:
        """Return whether the charger has synced phase limits."""
        return self._synced_phases

    async def set_current_limit(self, limit: Dict[Phase, int]) -> None:
        """Set the charger limit in amps."""
        if self._synced_phases:
            # If phases are synced, set all phases to the minimum value
            min_value = min(limit.values())
            self._current_limit = {phase: min_value for phase in Phase}
        else:
            # Update each phase individually
            for phase, value in limit.items():
                if phase in self._current_limit:
                    self._current_limit[phase] = value

    def get_current_limit(self) -> Optional[Dict[Phase, int]]:
        """Get the current limit of the charger in amps."""
        return self._current_limit

    def get_max_current_limit(self) -> Optional[Dict[Phase, int]]:
        """Get the configured maximum current limit of the charger in amps."""
        return self._max_current_limit

    def car_connected(self) -> bool:
        """Return whether the car is connected to the charger."""
        return self._is_car_connected

    def can_charge(self) -> bool:
        """Return whether the car can charge."""
        return self._can_charge_state

    def is_charging(self) -> bool:
        """Return whether the car is charging."""
        return self._is_charging

    # Test helper methods
    def set_car_connected(self, connected: bool) -> None:
        """Set whether a car is connected for testing."""
        self._is_car_connected = connected

    def set_can_charge(self, can_charge: bool) -> None:
        """Set whether the car can charge for testing."""
        self._can_charge_state = can_charge

    def set_is_charging(self, is_charging: bool) -> None:
        """Set whether the car is charging."""
        self._is_charging = is_charging

    def set_current_limits(self, limits: Dict[Phase, int]) -> None:
        """Manually set the current limits for testing."""
        self._current_limit = limits.copy()

    def set_max_limits(self, limits: Dict[Phase, int]) -> None:
        """Manually set the max current limits for testing."""
        self._max_current_limit = limits.copy()

    async def async_setup(self) -> None:
        """Set up the mock charger."""
        pass

    async def async_unload(self) -> None:
        """Unload the mock charger."""
        pass
