"""Keba Charger implementation."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from ..const import CHARGER_DOMAIN_KEBA, Phase  # noqa: TID252
from ..ha_device import HaDevice  # noqa: TID252
from .charger import Charger, PhaseMode

_LOGGER = logging.getLogger(__name__)


class KebaEntityMap:
    """
    Map Keba entities to their respective attributes.

    https://github.com/home-assistant/core/blob/dev/homeassistant/components/keba/sensor.py#L31
    """

    ChargingState = "charging_state"
    MaxCurrent = "max_current"


class KebaChargingStateMap:
    """
    Map charger statuses for entity 'charging_state' to their respective state values.

    @see https://sollis.de/wp-content/uploads/UDP-Programmieranleitung.pdf
    """

    Startup = "0"
    NotReady = "1"
    ReadyToCharge = "2"
    Charging = "3"
    Error = "4"
    Interrupted = "5"


class KebaCharger(HaDevice, Charger):
    """Implementation of the Charger class for Keba chargers."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
    ) -> None:
        """Initialize the Keba charger."""
        HaDevice.__init__(self, hass, device_entry)
        Charger.__init__(self, hass, config_entry, device_entry)
        self.refresh_entities()

    @staticmethod
    def is_charger_device(device: DeviceEntry) -> bool:
        """Check if the given device is a Keba charger."""
        return any(
            id_domain == CHARGER_DOMAIN_KEBA for id_domain, _ in device.identifiers
        )

    async def async_setup(self) -> None:
        """Set up the charger."""

    def set_phase_mode(self, mode: PhaseMode, _phase: Phase | None = None) -> None:
        """Set the phase mode of the charger."""
        if mode not in PhaseMode:
            msg = "Invalid mode. Must be 'single' or 'multi'."
            raise ValueError(msg)
        # TODO(Dirk): Implement the logic to set the phase mode for # noqa: FIX002
        # chargers.
        # https://github.com/dirkgroenen/hass-evse-load-balancer/issues/9

    async def set_current_limit(self, limit: dict[Phase, int]) -> None:
        """
        Set the current limit for the charger.

        As Keba only support to set the current limit for all phases
        we'll have to get the lowest value.
        """
        await self.hass.services.async_call(
            domain=CHARGER_DOMAIN_KEBA,
            service="set_current",
            service_data={
                "device_id": self.device_entry.id,
                "current": min(limit.values()),
            },
            blocking=True,
        )

    def get_current_limit(self) -> dict[Phase, int] | None:
        """See base class for correct implementation of this method."""
        state = self._get_entity_state_by_unique_id(
            self._compose_unique_id(KebaEntityMap.MaxCurrent)
        )
        if state is None:
            _LOGGER.warning(
                (
                    "MaX Charger limit not available. ",
                    "Make sure the required entity ",
                    "({KebaEntityMap.MaxCurrent}) is enabled",
                )
            )
            return None

        return dict.fromkeys(Phase, int(state))

    def get_max_current_limit(self) -> dict[Phase, int] | None:
        """
        Return maximum configured current for the charger.

        The KEBA charger integration does not provide a way to get
        the maximum current limit, so we return a default value representing
        the charger's maximum current limit.
        """
        return dict.fromkeys(Phase, 32)

    def has_synced_phase_limits(self) -> bool:
        """
        Return whether the charger has synced phase limits.

        Currently not supported - but can be done by setting correct
        phase control or 'master charger' circuit control
        """
        return True

    def _get_status(self) -> str | None:
        return self._get_entity_state_by_unique_id(
            self._compose_unique_id(KebaEntityMap.ChargingState)
        )

    def car_connected(self) -> bool:
        """See abstract Charger class for correct implementation of this method."""
        status = self._get_status()
        return status in [
            KebaChargingStateMap.ReadyToCharge,
            KebaChargingStateMap.Charging,
            KebaChargingStateMap.Interrupted,
        ]

    def can_charge(self) -> bool:
        """See abstract Charger class for correct implementation of this method."""
        status = self._get_status()
        return status in [
            KebaChargingStateMap.ReadyToCharge,
            KebaChargingStateMap.Charging,
        ]

    async def async_unload(self) -> None:
        """Unload the charger."""

    def _compose_unique_id(self, entity_key: str) -> str:
        """Compose a unique ID for the Keba charger entity."""
        return f"{self.device_entry.id}_{entity_key}"
