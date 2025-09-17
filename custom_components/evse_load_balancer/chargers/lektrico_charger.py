"""Lektri.co Charger implementation."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from ..const import CHARGER_DOMAIN_LEKTRICO, Phase  # noqa: TID252
from ..ha_device import HaDevice  # noqa: TID252
from .charger import Charger, PhaseMode

_LOGGER = logging.getLogger(__name__)


class LektricoEntityMap:
    """
    Map Lektri.co entities to their respective attributes.

    https://github.com/home-assistant/core/blob/dev/homeassistant/components/lektrico/sensor.py
    https://github.com/home-assistant/core/blob/dev/homeassistant/components/lektrico/number.py
    https://github.com/home-assistant/core/blob/dev/homeassistant/components/lektrico/switch.py
    """

    Status = "state"
    DynamicChargerLimit = "dynamic_limit"
    MaxChargerLimit = "installation_current"
    ForceSinglePhase = "force_single_phase"


class LektricoStatusMap:
    """
    Map Lektri.co charger statuses to their respective string representations.

    States taken from here: @see https://github.com/home-assistant/core/blob/dev/homeassistant/components/lektrico/sensor.py#L60
    """

    Available = "available"
    Charging = "charging"
    Connected = "connected"
    Error = "error"
    Locked = "locked"
    Authentication = "need_auth"
    Paused = "paused"
    PausedByScheduler = "paused_by_scheduler"
    Updating = "updating_firmware"


# Hardware limits for Lektri.co
LEKTRICO_HW_MAX_CURRENT = 32
LEKTRICO_HW_MIN_CURRENT = 0  # 0 == pause


class LektricoCharger(HaDevice, Charger):
    """Implementation of the Charger class for Lektri.co chargers."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
    ) -> None:
        """Initialize the Lektri.co charger."""
        HaDevice.__init__(self, hass, device_entry)
        Charger.__init__(self, hass, config_entry, device_entry)
        self.refresh_entities()

    @staticmethod
    def is_charger_device(device: DeviceEntry) -> bool:
        """Check if the given device is an Lektri.co charger."""
        return any(
            id_domain == CHARGER_DOMAIN_LEKTRICO for id_domain, _ in device.identifiers
        )

    async def async_setup(self) -> None:
        """Set up the charger."""

    async def set_phase_mode(
        self, mode: PhaseMode, _phase: Phase | None = None
    ) -> None:
        """Set the phase mode of the charger."""
        if mode not in PhaseMode:
            msg = "Invalid mode. Must be 'single' or 'multi'."
            raise ValueError(msg)

        # Get the force_single_phase switch entity
        force_single_phase_entity_id = self._get_entity_id_by_key(
            LektricoEntityMap.ForceSinglePhase
        )

        # Determine the switch state based on the desired phase mode
        # True = force single phase (PhaseMode.SINGLE)
        # False = allow three phase (PhaseMode.MULTI)
        turn_on_single_phase = mode == PhaseMode.SINGLE

        # Call the appropriate Home Assistant switch service
        service = "turn_on" if turn_on_single_phase else "turn_off"
        await self.hass.services.async_call(
            domain="switch",
            service=service,
            service_data={"entity_id": force_single_phase_entity_id},
            blocking=True,
        )

    async def set_current_limit(self, limit: dict[Phase, int]) -> None:
        """
        Set the current limit for the charger.

        As Lektri.co only support to set the current limit for all phases
        we'll have to get the lowest value.
        """
        # Get the entity_id for the dynamic_limit number entity
        dynamic_limit_entity_id = self._get_entity_id_by_key(
            LektricoEntityMap.DynamicChargerLimit
        )

        value = min(limit.values())
        value = max(LEKTRICO_HW_MIN_CURRENT, min(value, LEKTRICO_HW_MAX_CURRENT))

        # Call the Home Assistant number.set_value service
        await self.hass.services.async_call(
            domain="number",
            service="set_value",
            service_data={
                "entity_id": dynamic_limit_entity_id,
                "value": value,
            },
            blocking=True,
        )

    def get_current_limit(self) -> dict[Phase, int] | None:
        """See base class for correct implementation of this method."""
        state = self._get_entity_state_by_key(LektricoEntityMap.DynamicChargerLimit)
        return dict.fromkeys(Phase, int(state))

    def get_max_current_limit(self) -> dict[Phase, int] | None:
        """Return maximum configured current for the charger."""
        state = self._get_entity_state_by_key(LektricoEntityMap.MaxChargerLimit)
        return dict.fromkeys(Phase, int(state))

    def has_synced_phase_limits(self) -> bool:
        """Return whether the charger has synced phase limits."""
        return True

    def _get_status(self) -> str | None:
        return self._get_entity_state_by_key(
            LektricoEntityMap.Status,
        )

    def car_connected(self) -> bool:
        """See abstract Charger class for correct implementation of this method."""
        status = self._get_status()
        return status in [
            LektricoStatusMap.Connected,
            LektricoStatusMap.Charging,
            LektricoStatusMap.Paused,
            LektricoStatusMap.PausedByScheduler,
        ]

    def can_charge(self) -> bool:
        """See abstract Charger class for correct implementation of this method."""
        status = self._get_status()
        return status in [
            LektricoStatusMap.Connected,
            LektricoStatusMap.Charging,
        ]

    def is_charging(self) -> bool:
        """See abstract Charger class for correct implementation of this method."""
        status = self._get_status()
        return status == LektricoStatusMap.Charging

    async def async_unload(self) -> None:
        """Unload the Lektri.co charger."""
