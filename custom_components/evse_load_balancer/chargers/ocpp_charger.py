"""OCPP Charger implementation."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from ..const import CHARGER_DOMAIN_OCPP, Phase  # noqa: TID252
from ..ha_device import HaDevice  # noqa: TID252
from .charger import Charger, PhaseMode

_LOGGER = logging.getLogger(__name__)


class OcppEntityMap:
    """
    Map OCPP entities to their respective attributes.

    Based on the enums and measurands from the OCPP integration:
    https://github.com/lbbrhzn/ocpp/blob/main/custom_components/ocpp/enums.py
    """

    # Status entities from HAChargerStatuses
    Status = "Status"
    StatusConnector = "Status.Connector"

    # Current limit via number metric
    # https://github.com/lbbrhzn/ocpp/blob/main/custom_components/ocpp/number.py
    MaximumCurrent = "maximum_current"

    TransactionId = "transaction_id"


class OcppStatusMap:
    """
    Map OCPP charger statuses to their respective string representations.

    OCPP charger statuses as defined in the OCPP protocol.
    These are typically available through the Status or Status.Connector sensors.
    """

    Available = "Available"
    Preparing = "Preparing"
    Charging = "Charging"
    SuspendedEVSE = "SuspendedEVSE"
    SuspendedEV = "SuspendedEV"
    Finishing = "Finishing"
    Reserved = "Reserved"
    Unavailable = "Unavailable"
    Faulted = "Faulted"


class OcppCharger(HaDevice, Charger):
    """Implementation of the Charger class for OCPP chargers."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
    ) -> None:
        """Initialize the OCPP charger."""
        HaDevice.__init__(self, hass, device_entry)
        Charger.__init__(self, hass, config_entry, device_entry)
        self.refresh_entities()

    @staticmethod
    def is_charger_device(device: DeviceEntry) -> bool:
        """Check if the given device is an OCPP charger."""
        return any(
            id_domain == CHARGER_DOMAIN_OCPP for id_domain, _ in device.identifiers
        )

    async def async_setup(self) -> None:
        """Set up the charger."""

    def set_phase_mode(self, mode: PhaseMode, _phase: Phase | None = None) -> None:
        """Set the phase mode of the charger."""
        if mode not in PhaseMode:
            msg = "Invalid mode. Must be 'single' or 'multi'."
            raise ValueError(msg)
        # Phase mode setting is not currently implemented for OCPP chargers.
        # This may require using the OCPP configuration or smart charging profiles.

    async def set_current_limit(self, limit: dict[Phase, int]) -> None:
        """
        Set the current limit for the charger.

        OCPP chargers typically support setting current limits through
        the set_charge_rate service or smart charging profiles.
        As OCPP may not support per-phase limits, we'll use the minimum value.
        """
        min_current = min(limit.values())

        transaction_id = self._get_entity_id_by_key(OcppEntityMap.TransactionId)

        try:
            await self.hass.services.async_call(
                domain=CHARGER_DOMAIN_OCPP,
                service="set_charge_rate",
                service_data={
                    "custom_profile": {
                        "transactionId": transaction_id,
                        "chargingProfileId": 1,
                        "stackLevel": 0,
                        "chargingProfilePurpose": "ChargePointMaxProfile",
                        "chargingProfileKind": "Relative",
                        "chargingSchedule": {
                            "chargingRateUnit": "A",
                            "chargingSchedulePeriod": [
                                {"startPeriod": 0, "limit": min_current}
                            ]
                        }
                    },
                    "conn_id": 1
                },
                blocking=True,
            )
        except (ValueError, RuntimeError, TimeoutError) as e:
            _LOGGER.warning(
                "Failed to set current limit for OCPP charger %s: %s",
                self.device_entry.id,
                e,
            )

    def get_current_limit(self) -> dict[Phase, int] | None:
        """Get the current limit of the charger in amps."""
        # Try to get the current offered first, then fall back to current import
        state = self._get_entity_state_by_key(OcppEntityMap.MaximumCurrent)

        if state is None:
            _LOGGER.warning(
                "Current limit not available for OCPP charger %s. "
                "Make sure the required entity (%s) is enabled and available",
                self.device_entry.id,
                OcppEntityMap.MaximumCurrent,
            )
            return None

        try:
            current_value = int(float(state))
            return dict.fromkeys(Phase, current_value)
        except (ValueError, TypeError) as e:
            _LOGGER.warning(
                "Failed to parse current limit value '%s' for OCPP charger %s: %s",
                state,
                self.device_entry.id,
                e,
            )
            return None

    def get_max_current_limit(self) -> dict[Phase, int] | None:
        """Get the configured maximum current limit of the charger in amps."""
        # TODO: Figure out from OCPP Spec how to retrieve a charger's max current limit  # noqa: E501, FIX002, TD002, TD003
        _LOGGER.info(
            "No maximum current limit information available for OCPP charger %s, "
            "using default 32A",
            self.device_entry.id,
        )
        return dict.fromkeys(Phase, 32)

    def has_synced_phase_limits(self) -> bool:
        """
        Return whether the charger has synced phase limits.

        OCPP typically doesn't support per-phase current limits,
        so we return False to indicate all phases use the same limit.
        """
        return False

    def _get_status(self) -> str | None:
        """Get the current status of the OCPP charger."""
        # Try connector status first, then general status
        status = None

        try:
            status = self._get_entity_state_by_key(
                OcppEntityMap.StatusConnector,
            )
        except ValueError as e:
            _LOGGER.debug(
                "Failed to get status for OCPP charger by entity '%s': '%s'",
                OcppEntityMap.StatusConnector,
                e,
            )

        if status is None:
            status = self._get_entity_state_by_key(
                OcppEntityMap.Status,
            )

        return status

    def car_connected(self) -> bool:
        """Car is connected to the charger and ready to receive charge."""
        status = self._get_status()

        # Consider the car connected if the charger is in any of these states
        connected_statuses = [
            OcppStatusMap.Preparing,
            OcppStatusMap.Charging,
            OcppStatusMap.SuspendedEVSE,
            OcppStatusMap.SuspendedEV,
            OcppStatusMap.Finishing,
        ]

        return status in connected_statuses

    def can_charge(self) -> bool:
        """Return whether the car is connected and charging or accepting charge."""
        status = self._get_status()

        charging_statuses = [
            OcppStatusMap.Preparing,
            OcppStatusMap.Charging,
            OcppStatusMap.SuspendedEV,
        ]

        return status in charging_statuses

    async def async_unload(self) -> None:
        """Unload the OCPP charger."""
