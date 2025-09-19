"""Easee Charger implementation."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from ..const import CHARGER_DOMAIN_EASEE, Phase  # noqa: TID252
from ..ha_device import HaDevice  # noqa: TID252
from .charger import Charger, PhaseMode

_LOGGER = logging.getLogger(__name__)


class EaseeEntityMap:
    """
    Map Easee entities to their respective attributes.

    https://github.com/nordicopen/easee_hass/blob/master/custom_components/easee/const.py
    """

    Status = "easee_status"
    DynamicChargerLimit = "dynamic_charger_limit"
    MaxChargerLimit = "max_charger_limit"


class EaseeStatusMap:
    """
    Map Easee charger statuses to their respective string representations.

    Enum mapping for Status - Op Mode (109), which is mapped
    by the easee_hass integration to strings
    @see https://developer.easee.com/docs/enumerations
    @see https://github.com/nordicopen/easee_hass/blob/master/custom_components/easee/const.py
    """

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

    @staticmethod
    def is_charger_device(device: DeviceEntry) -> bool:
        """Check if the given device is an Easee charger."""
        return any(
            id_domain == CHARGER_DOMAIN_EASEE for id_domain, _ in device.identifiers
        )

    async def async_setup(self) -> None:
        """Set up the charger."""

    def set_phase_mode(self, mode: PhaseMode, _phase: Phase | None = None) -> None:
        """Set the phase mode of the charger."""
        if mode not in PhaseMode:
            msg = "Invalid mode. Must be 'single' or 'multi'."
            raise ValueError(msg)
        # TODO(Dirk): Implement the logic to set the phase mode for Easee # noqa: FIX002
        # chargers.
        # https://github.com/dirkgroenen/hass-evse-load-balancer/issues/9

    async def set_current_limit(self, limit: dict[Phase, int]) -> None:
        """
        Set the current limit for the charger.

        As Easee only support to set the current limit for all phases
        we'll have to get the lowest value.
        """
        await self.hass.services.async_call(
            domain=CHARGER_DOMAIN_EASEE,
            service="set_charger_dynamic_limit",
            service_data={
                "device_id": self.device_entry.id,
                "current": min(limit.values()),
                "time_to_live": 0,
            },
            blocking=True,
        )

    def get_current_limit(self) -> dict[Phase, int] | None:
        """See base class for correct implementation of this method."""
        state = self._get_entity_state_by_translation_key(
            EaseeEntityMap.DynamicChargerLimit
        )
        if state is None:
            _LOGGER.warning(
                (
                    "Mas Charger limit not available. ",
                    "Make sure the required entity ",
                    "({EaseeEntityMap.DynamicChargerLimit}) is enabled",
                )
            )
            return None

        return dict.fromkeys(Phase, int(state))

    def get_max_current_limit(self) -> dict[Phase, int] | None:
        """Return maximum configured current for the charger."""
        state = self._get_entity_state_by_translation_key(
            EaseeEntityMap.MaxChargerLimit
        )
        if state is None:
            _LOGGER.warning(
                (
                    "Mas Charger limit not available. ",
                    "Make sure the required entity ",
                    "({EaseeEntityMap.MaxChargerLimit}) is enabled",
                )
            )
            return None
        return dict.fromkeys(Phase, int(state))

    def has_synced_phase_limits(self) -> bool:
        """
        Return whether the charger has synced phase limits.

        Currently not supported - but can be done by setting correct
        phase control or 'master charger' circuit control
        """
        return True

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

    def can_charge(self) -> bool:
        """See abstract Charger class for correct implementation of this method."""
        status = self._get_status()
        return status in [
            EaseeStatusMap.AwaitingStart,
            EaseeStatusMap.Charging,
            EaseeStatusMap.ReadyToCharge,
        ]

    def is_charging(self) -> bool:
        """See abstract Charger class for correct implementation of this method."""
        status = self._get_status()
        return status == EaseeStatusMap.Charging

    async def async_unload(self) -> None:
        """Unload the Easee charger."""
