"""Easee Charger implementation."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from ..const import CHARGER_DOMAIN_EASEE, Phase
from ..ha_device import HaDevice
from .charger import Charger, PhaseMode

_LOGGER = logging.getLogger(__name__)

# Map Easee Entities based on the easee_hass
# integration translation keys.
# https://github.com/nordicopen/easee_hass/blob/master/custom_components/easee/const.py


class EaseeEntityMap:
    """Map Easee entities to their respective attributes."""

    Status = "easee_status"
    DynamicChargerLimit = "dynamic_charger_limit"
    DynamicCircuitLimit = "dynamic_circuit_limit"
    MaxChargerCurrent = "max_charger_limit"


# Mapping attributes to known phases
# @see https://github.com/nordicopen/easee_hass/blob/master/custom_components/easee/const.py
EASEE_DYNAMIC_CIRCUIT_CURRENT_MAP = {
    Phase.L1: "state_dynamicCircuitCurrentP1",
    Phase.L2: "state_dynamicCircuitCurrentP2",
    Phase.L3: "state_dynamicCircuitCurrentP3",
}

# Enum mapping for Status - Op Mode (109), which is mapped
# by the easee_hass integration to strings
# @see https://developer.easee.com/docs/enumerations
# @see https://github.com/nordicopen/easee_hass/blob/master/custom_components/easee/const.py


class EaseeStatusMap:
    """Map Easee charger statuses to their respective string representations."""

    Disconnected = "disconnected"
    AwaitingStart = "awaiting_start"
    Charging = "charging"
    Completed = "completed"
    Error = "error"
    ReadyToCharge = "ready_to_charge"
    AwaitingAuthorization = "awaiting_authorization"
    DeAuthorization = "de_authorizing"


class EaseeCharger(HaDevice, Charger):
    """Implementation of the Charger class for Easee chargers."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
    ) -> None:
        """Initialize the Easee charger."""
        HaDevice.__init__(self, hass, device_entry)
        Charger.__init__(self, hass, config_entry, device_entry)
        self.refresh_entities()

    def set_phase_mode(self, mode: PhaseMode, phase: Phase) -> None:
        """Set the phase mode of the charger."""
        if mode not in PhaseMode:
            msg = "Invalid mode. Must be 'single' or 'multi'."
            raise ValueError(msg)
        # Implement the logic to set the phase mode for Easee chargers

    async def set_current_limit(self, limit: dict[Phase, int]) -> None:
        """Set the current limit for the charger."""
        max_current = self._get_entity_state_by_translation_key(
            EaseeEntityMap.MaxChargerCurrent
        )
        for phase, current in limit.items():
            if current > max_current:
                _LOGGER.debug(
                    (
                        "New current for phase %s (%s) exceeds configured max charger "
                        "current %s. Setting limit to %s"
                    ),
                    phase,
                    current,
                    max_current,
                    max_current,
                )
                limit[phase] = max_current

        await self.hass.services.async_call(
            domain=CHARGER_DOMAIN_EASEE,
            service="set_circuit_dynamic_limit",
            service_data={
                "device_id": self.device_entry.id,
                "current_p1": limit[Phase.L1],
                "current_p2": limit[Phase.L2],
                "current_p3": limit[Phase.L3],
                "time_to_live": 0,
            },
            blocking=True,
        )

    def get_current_limit(self) -> dict[Phase, int]:
        """See base class for correct implementation of this method."""
        state_attrs = self._get_entity_state_attrs_by_translation_key(
            EaseeEntityMap.DynamicCircuitLimit
        )
        if state_attrs is None:
            _LOGGER.warning("Dynamic Circuit Limit not available")
            return dict.fromkeys(Phase)
        return {
            phase: state_attrs.get(EASEE_DYNAMIC_CIRCUIT_CURRENT_MAP[phase], None)
            for phase in Phase
        }

    def _get_status(self) -> str | None:
        return self._get_entity_state_by_translation_key(
            EaseeEntityMap.Status,
        )

    def car_connected(self) -> bool:
        """See abstract Charger class for correct implementation of this method."""
        status = self._get_status()
        return status in [
            EaseeStatusMap.AwaitingStart,
            EaseeStatusMap.Charging,
            EaseeStatusMap.Completed,
            EaseeStatusMap.ReadyToCharge,
        ]

    def is_charging(self) -> bool:
        """See abstract Charger class for correct implementation of this method."""
        status = self._get_status()
        return status in [
            EaseeStatusMap.Charging,
        ]
