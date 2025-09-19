"""Zaptec Charger implementation."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from ..const import CHARGER_DOMAIN_ZAPTEC  # noqa: TID252
from ..ha_device import HaDevice  # noqa: TID252
from ..meters.meter import Phase  # Use the correct import path  # noqa: TID252
from .charger import Charger, PhaseMode

_LOGGER = logging.getLogger(__name__)

# Constants for the Zaptec integration


class ZaptecEntityMap:
    """Map of Zaptec entity translation keys."""

    MaxChargingCurrent = "charger_max_current"
    AvailableCurrent = "available_current"
    Status = "charger_operation_mode"


class ZaptecStatusMap:
    """
    Map of Zaptec charger statuses.

    See https://github.com/custom-components/zaptec/blob/master/custom_components/zaptec/sensor.py#L43-L49
    """

    Unknown = "unknown"
    Disconnected = "disconnected"
    ConnectedRequesting = "connected_requesting"
    ConnectedCharging = "connected_charging"
    ConnectedFinished = "connected_finished"


class ZaptecCharger(HaDevice, Charger):
    """Implementation of the Charger class for Zaptec chargers."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
    ) -> None:
        """Initialize the Zaptec charger."""
        HaDevice.__init__(self, hass, device_entry)
        Charger.__init__(self, hass, config_entry, device_entry)
        self.refresh_entities()

    @staticmethod
    def is_charger_device(device: DeviceEntry) -> bool:
        """Check if the given device is a Zaptec charger."""
        return any(
            id_domain == CHARGER_DOMAIN_ZAPTEC for id_domain, _ in device.identifiers
        )

    async def async_setup(self) -> None:
        """Set up the charger."""

    def set_phase_mode(self, mode: PhaseMode, _phase: Phase | None = None) -> None:
        """Set the phase mode of the charger."""
        if mode not in PhaseMode:
            msg = "Invalid mode. Must be 'single' or 'multi'."
            raise ValueError(msg)

        # TODO(Dirk): Implement the logic to set the phase mode # noqa: FIX002
        # https://github.com/dirkgroenen/hass-evse-load-balancer/issues/9

    async def set_current_limit(self, limit: dict[Phase, int]) -> None:
        """Set the current limit for the Zaptec charger."""
        # Get the entity_id for the charger_max_current number entity
        charger_max_current_entity_id = self._get_entity_id_by_translation_key(
            ZaptecEntityMap.MaxChargingCurrent
        )

        value = min(limit.values())

        # Call the Home Assistant number.set_value service
        await self.hass.services.async_call(
            domain="number",
            service="set_value",
            service_data={
                "entity_id": charger_max_current_entity_id,
                "value": value,
            },
            blocking=True,
        )

    def get_current_limit(self) -> dict[Phase, int] | None:
        """Get the current limit set on the charger."""
        entity_state = self._get_entity_state_by_translation_key(
            ZaptecEntityMap.MaxChargingCurrent
        )

        try:
            current_value = int(float(entity_state))
            return dict.fromkeys(Phase, current_value)
        except (ValueError, TypeError):
            _LOGGER.exception(
                "Could not convert current limit '%s' to number", entity_state
            )
            return None

    def get_max_current_limit(self) -> dict[Phase, int] | None:
        """Return maximum configured current for the charger."""
        state = self._get_entity_state_by_translation_key(
            ZaptecEntityMap.AvailableCurrent
        )
        if state is None:
            _LOGGER.warning(
                (
                    "Max charger limit not available. "
                    "Make sure the required entity (%s) is enabled"
                ),
                ZaptecEntityMap.AvailableCurrent,
            )
            return None

        try:
            # Zaptec returns the same max value for all phases
            max_value = int(float(state))
        except (ValueError, TypeError):
            _LOGGER.exception("Could not convert max current '%s' to number", state)
            return None

        return {
            Phase.L1: max_value,
            Phase.L2: max_value,
            Phase.L3: max_value,
        }

    def has_synced_phase_limits(self) -> bool:
        """Return whether the charger has synced phase limits."""
        return True

    def _get_status(self) -> str | None:
        """Get the current status of the charger."""
        return self._get_entity_state_by_translation_key(ZaptecEntityMap.Status)

    def car_connected(self) -> bool:
        """Check if a car is connected to the charger."""
        status = self._get_status()
        return status in (
            ZaptecStatusMap.ConnectedRequesting,
            ZaptecStatusMap.ConnectedCharging,
            ZaptecStatusMap.ConnectedFinished,
        )

    def can_charge(self) -> bool:
        """Check if the charger is in a state where it can charge."""
        status = self._get_status()
        return status in (
            ZaptecStatusMap.ConnectedCharging,
            ZaptecStatusMap.ConnectedRequesting,
        )

    def is_charging(self) -> bool:
        """Check if the charger is charging."""
        status = self._get_status()
        return status == ZaptecStatusMap.ConnectedCharging

    async def async_unload(self) -> None:
        """Unload the charger."""
