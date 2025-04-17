import logging
from typing import Optional
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import (
    DeviceEntry,
)

from ..ha_device import HaDevice
from .charger import (Charger, PhaseMode)
from ..const import CHARGER_DOMAIN_EASEE, Phase

_LOGGER = logging.getLogger(__name__)

# Map Easee Entities based on the easee_hass
# integration translation keys.
# https://github.com/nordicopen/easee_hass/blob/master/custom_components/easee/const.py


class EaseeEntityMap:
    Status = "easee_status"
    DynamicChargerLimit = "dynamic_charger_limit"
    MaxChargerCurrent = "max_charger_limit"


# Enum mapping for Status - Op Mode (109), which is mapped
# by the easee_hass integration to strings
# @see https://developer.easee.com/docs/enumerations
# @see https://github.com/nordicopen/easee_hass/blob/master/custom_components/easee/const.py
class EaseeStatusMap:
    Disconnected = "disconnected"
    AwaitingStart = "awaiting_start"
    Charging = "charging"
    Completed = "completed"
    Error = "error"
    ReadyToCharge = "ready_to_charge"
    AwaitingAuthorization = "awaiting_authorization"
    DeAuthorization = "de_authorizing"


class EaseeCharger(HaDevice, Charger):
    """
    Implementation of the Charger class for Easee chargers.
    """

    def __init__(self, hass: HomeAssistant, device_entry: DeviceEntry):
        HaDevice.__init__(self, hass, device_entry)
        self.refresh_entities()

    def set_phase_mode(self, mode: PhaseMode, phase: int):
        if mode not in PhaseMode:
            raise ValueError("Invalid mode. Must be 'single' or 'multi'.")
        # Implement the logic to set the phase mode for Easee chargers

    async def set_current_limit(self, limit: dict[Phase, int]):
        if limit <= 0:
            raise ValueError("Limit must be a positive integer.")

        max_current = self._get_entity_state_by_translation_key(EaseeEntityMap.MaxChargerCurrent)
        if max_current is not None and max_current < limit:
            _LOGGER.debug("New current %s exceeds configured max charger current %s. Setting limit to %s ", limit, max_current, limit)
            limit = max_current

        await self.hass.services.async_call(
            domain=CHARGER_DOMAIN_EASEE,
            service="set_circuit_dynamic_limit",
            service_data={
                "device_id": self.device_entry.id,
                "current_p1": limit,
                "current_p2": limit,
                "current_p3": limit,
                "time_to_live": 0
            },
            blocking=True,
        )

    def get_current_limit(self) -> Optional[int]:
        return self._get_entity_state_by_translation_key(
            EaseeEntityMap.DynamicChargerLimit,
            int
        )

    def _get_status(self) -> Optional[str]:
        return self._get_entity_state_by_translation_key(
            EaseeEntityMap.Status,
        )

    def car_connected(self) -> bool:
        """
        See abstract Charger class for correct implementation of car_connected()
        """
        status = self._get_status()
        return status in [
            EaseeStatusMap.AwaitingStart,
            EaseeStatusMap.Charging,
            EaseeStatusMap.Completed,
            EaseeStatusMap.ReadyToCharge,
        ]

    def is_charging(self) -> bool:
        """
        See abstract Charger class for correct implementation of is_charging()
        """
        status = self._get_status()
        return status in [
            EaseeStatusMap.Charging,
        ]
