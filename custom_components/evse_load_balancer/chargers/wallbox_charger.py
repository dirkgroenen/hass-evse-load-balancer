"""Wallbox Charger implementation."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from ..const import CHARGER_DOMAIN_WALLBOX, Phase  # noqa: TID252
from ..ha_device import HaDevice  # noqa: TID252
from .charger import Charger, PhaseMode

_LOGGER = logging.getLogger(__name__)


class WallboxEntityMap:
    """
    Map Wallbox entities to their respective translation keys.

    https://github.com/home-assistant/core/blob/dev/homeassistant/components/wallbox/number.py
    https://github.com/home-assistant/core/blob/dev/homeassistant/components/wallbox/sensor.py
    """

    DynamicChargerLimit = "maximum_charging_current"
    MaxChargerLimit = "max_available_power"
    Status = "status_description"


class WallboxStatusMap:
    """
    Normalized status values used by the adapter.

    Values mirror the Wallbox integration `ChargerStatus` strings.
    https://github.com/home-assistant/core/blob/dev/homeassistant/components/wallbox/const.py
    """

    Charging = "Charging"
    Discharging = "Discharging"
    Paused = "Paused"
    Scheduled = "Scheduled"
    WaitingForCarDemand = "Waiting for car demand"
    Waiting = "Waiting"
    Disconnected = "Disconnected"
    Error = "Error"
    Ready = "Ready"
    Locked = "Locked"
    LockedCarConnected = "Locked, car connected"
    Updating = "Updating"
    WaitingInQueuePowerSharing = "Waiting in queue by Power Sharing"
    WaitingInQueuePowerBoost = "Waiting in queue by Power Boost"
    WaitingMidFailed = "Waiting MID failed"
    WaitingMidSafety = "Waiting MID safety margin exceeded"
    WaitingInQueueEcoSmart = "Waiting in queue by Eco-Smart"
    Unknown = "Unknown"


class WallboxCharger(HaDevice, Charger):
    """Implementation of the Charger class for Wallbox chargers."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
    ) -> None:
        """Initialize the Wallbox charger."""
        HaDevice.__init__(self, hass, device_entry)
        Charger.__init__(self, hass, config_entry, device_entry)
        self.refresh_entities()

    @staticmethod
    def is_charger_device(device: DeviceEntry) -> bool:
        """Check if the given device is a Wallbox charger."""
        return any(
            id_domain == CHARGER_DOMAIN_WALLBOX
            for id_domain, _ in device.identifiers
        )

    async def async_setup(self) -> None:
        """Set up the charger (no-op)."""

    def set_phase_mode(self, mode: PhaseMode, _phase: Phase | None = None) -> None:
        """Set the phase mode (no-op for Wallbox)."""
        if mode not in PhaseMode:
            msg = "Invalid mode. Must be 'single' or 'multi'."
            raise ValueError(msg)

    def has_synced_phase_limits(self) -> bool:
        """Wallbox number entity exposes a single max current value (global)."""
        return True

    async def set_current_limit(self, limit: dict[Phase, int]) -> None:
        """
        Set the charger current limit.

        The official Wallbox integration exposes the charging current as a
        `number` entity. We update that entity using the common
        `number.set_value` service with the entity_id and a numeric `value`.
        """
        amps = int(min(limit.values()))

        entity_id = self._get_entity_id_by_translation_key(
            WallboxEntityMap.DynamicChargerLimit
        )

        await self.hass.services.async_call(
            domain="number",
            service="set_value",
            service_data={"entity_id": entity_id, "value": amps},
            blocking=True,
        )

    def get_current_limit(self) -> dict[Phase, int] | None:
        """Return the currently configured charging limit (from the `number` entity)."""
        state = self._get_entity_state_by_translation_key(
            WallboxEntityMap.DynamicChargerLimit
        )
        if state is None:
            _LOGGER.warning(
                "Wallbox dynamic charger limit not available for device %s",
                self.device_entry.id,
            )
            return None
        try:
            return dict.fromkeys(Phase, int(float(state)))
        except (ValueError, TypeError):
            _LOGGER.warning("Unable to parse Wallbox dynamic limit state: %s", state)
            return None

    def get_max_current_limit(self) -> dict[Phase, int] | None:
        """Return the configured maximum charging current."""
        state = self._get_entity_state_by_translation_key(
            WallboxEntityMap.MaxChargerLimit
        )
        if state is None:
            _LOGGER.warning(
                "Wallbox max charger limit not available for device %s",
                self.device_entry.id,
            )
            return None
        try:
            return dict.fromkeys(Phase, int(float(state)))
        except (ValueError, TypeError):
            _LOGGER.warning("Unable to parse Wallbox max limit state: %s", state)
            return None

    def _get_status(self) -> str | None:
        return self._get_entity_state_by_translation_key(WallboxEntityMap.Status)

    def car_connected(self) -> bool:
        """Return whether a car is connected to the charger."""
        status = self._get_status()
        return status in (
            WallboxStatusMap.Charging,
            WallboxStatusMap.Discharging,
            WallboxStatusMap.Paused,
            WallboxStatusMap.Scheduled,
            WallboxStatusMap.WaitingForCarDemand,
            WallboxStatusMap.Waiting,
            WallboxStatusMap.LockedCarConnected,
            WallboxStatusMap.WaitingInQueuePowerSharing,
            WallboxStatusMap.WaitingInQueuePowerBoost,
            WallboxStatusMap.WaitingInQueueEcoSmart,
            WallboxStatusMap.WaitingMidFailed,
            WallboxStatusMap.WaitingMidSafety,
        )

    def can_charge(self) -> bool:
        """Return whether the charger can deliver charge."""
        status = self._get_status()
        return status in (
            WallboxStatusMap.Charging,
            WallboxStatusMap.Discharging,
            WallboxStatusMap.WaitingForCarDemand,
            WallboxStatusMap.Paused,
        )

    def is_charging(self) -> bool:
        """Return whether the charger is actively charging."""
        status = self._get_status()
        return status == WallboxStatusMap.Charging

    async def async_unload(self) -> None:
        """Unload the Wallbox charger (no-op)."""
