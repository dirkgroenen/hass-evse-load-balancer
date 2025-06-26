"""Easee Charger implementation."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from ..const import CHARGER_DOMAIN_LEKTRICO_TRI, Phase  # noqa: TID252
from ..ha_device import HaDevice  # noqa: TID252
from .charger import Charger, PhaseMode

_LOGGER = logging.getLogger(__name__)


class LektricoTRIEntityMap:
    """
    Map Lektri.co TRI entities to their respective attributes.

    https://github.com/Lektrico/ha_lektrico/blob/main/custom_components/lektrico_custom/sensor.py
    """

    Status = "state"
    DynamicChargerLimit = "dynamic_limit"
    MaxChargerLimit = "installation_current"


class LektricoTRIStatusMap:
    """
    Map Lektri.co TRI charger statuses to their respective string representations.

    Possible states taken from here: @see https://github.com/Lektrico/ha_lektrico/blob/main/README.md
    Mapping to values taken from here: @see https://github.com/Lektrico/lektricowifi/blob/main/src/lektricowifi/lektricowifi.py#L384
    Couldn't find anywhere in official integration "ha_lektrico" github the values. After digging deeper found another repository 
    which seems to handle the communication with the charger - "lektricowifi". 
    """

    Available = "available"
    Connected = "connected"
    Authentication = "need_auth"
    Charging = "charging"
    Error = "error"
    Updating = "updating_firmware"
    Locked = "locked"
    Paused = "paused"
    PausedByScheduler = "paused_by_scheduler"

# Hardware limits for Lektri.co TRI
LEKTRICO_TRI_HW_MAX_CURRENT = 32
LEKTRICO_TRI_HW_MIN_CURRENT = 6


class LektricoTRICharger(HaDevice, Charger):
    """Implementation of the Charger class for Lektri.co TRI chargers."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
    ) -> None:
        """Initialize the Lektri.co TRI charger."""
        HaDevice.__init__(self, hass, device_entry)
        Charger.__init__(self, hass, config_entry, device_entry)
        self.refresh_entities()

    @staticmethod
    def is_charger_device(device: DeviceEntry) -> bool:
        """Check if the given device is an Lektri.co TRI charger."""
        return any(
            id_domain == CHARGER_DOMAIN_LEKTRICO_TRI for id_domain, _ in device.identifiers
        )
        # TODO(@lsc597): Not sure what must be written here

    async def async_setup(self) -> None:
        """Set up the charger."""

    def set_phase_mode(self, mode: PhaseMode, _phase: Phase | None = None) -> None:
        """Set the phase mode of the charger."""
        if mode not in PhaseMode:
            msg = "Invalid mode. Must be 'single' or 'multi'."
            raise ValueError(msg)
        # TODO(@lsc597): Lektri.co TRI is a 3-phase charger, but it can also be installed and work perfectly in 1-phase system.
        #                I don't know exactly what to write here in order to set the correct mode based on physical installation.
        #                The official integration provides a switch called "ForceSinglePhase" which might be used in order to get this info, 
        #                but the problem is that this switch is not saved in Flash, so it resets after every reboot.                                        

    async def set_current_limit(self, limit: dict[Phase, int]) -> None:
        """
        Set the current limit for the charger.
        As Lektri.co TRI only support to set the current limit for all phases
        we'll have to get the lowest value.
        """
        await self.hass.services.async_call(
            domain=CHARGER_DOMAIN_LEKTRICO_TRI,
            service="dynamic_limit", # TODO(@lsc597): Not sure the service is correct here.
            service_data={
                "device_id": self.device_entry.id,
                "current": min(limit.values()), # TODO(@lsc597): Need to make sure the values are ALWAYS between LEKTRICO_TRI_HW_MIN_CURRENT and LEKTRICO_TRI_HW_MAX_CURRENT.
                "time_to_live": 0,
            },
            blocking=True,
        )

    def get_current_limit(self) -> dict[Phase, int] | None:
        """See base class for correct implementation of this method."""
        state = self._get_entity_state_by_translation_key(
            LektricoTRIEntityMap.DynamicChargerLimit
        )
        if state is None:
            _LOGGER.warning(
                (
                    "Charger limit not available. ",
                    "Make sure the required entity ",
                    "({LektricoTRIEntityMap.DynamicChargerLimit}) is enabled",
                )
            )
            return None

        return dict.fromkeys(Phase, int(state))

    def get_max_current_limit(self) -> dict[Phase, int] | None:
        """Return maximum configured current for the charger."""
        state = self._get_entity_state_by_translation_key(
            LektricoTRIEntityMap.MaxChargerLimit
        )
        if state is None:
            _LOGGER.warning(
                (
                    "Max Charger limit not available. ",
                    "Make sure the required entity ",
                    "({LektricoTRIEntityMap.MaxChargerLimit}) is enabled",
                )
            )
            return None
        return dict.fromkeys(Phase, int(state))

    def has_synced_phase_limits(self) -> bool:
        """
        Return whether the charger has synced phase limits.
        """
        return True

    def _get_status(self) -> str | None:
        return self._get_entity_state_by_translation_key(
            LektricoTRIEntityMap.Status,
        )

    def car_connected(self) -> bool:
        """See abstract Charger class for correct implementation of this method."""
        status = self._get_status()
        return status in [
            LektricoTRIStatusMap.Connected,
            LektricoTRIStatusMap.Charging,
            LektricoTRIStatusMap.Paused,
            LektricoTRIStatusMap.PausedByScheduler,
        ]

    def can_charge(self) -> bool:
        """See abstract Charger class for correct implementation of this method."""
        status = self._get_status()
        return status in [
            LektricoTRIStatusMap.Connected,
            LektricoTRIStatusMap.Charging,
        ]

    async def async_unload(self) -> None:
        """Unload the Easee charger."""
