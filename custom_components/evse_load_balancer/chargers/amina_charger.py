"""Amina Charger implementation using direct MQTT communication."""

import logging
from enum import StrEnum, unique

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from ..const import (  # noqa: TID252
    CHARGER_MANUFACTURER_AMINA,
    HA_INTEGRATION_DOMAIN_MQTT,
    Z2M_DEVICE_IDENTIFIER_DOMAIN,
    Phase,
)
from .charger import Charger, PhaseMode
from .util.zigbee2mqtt import Zigbee2Mqtt


@unique
class AminaPropertyMap(StrEnum):
    """Map Amina charger properties."""

    ChargeLimit = "charge_limit"
    SinglePhase = "single_phase"
    EvConnected = "ev_connected"
    EvStatus = "ev_status"
    Charging = "charging"
    State = "state"

    @staticmethod
    def gettable() -> list[StrEnum]:
        """Define properties that can be fetched via a /get request."""
        return [
            AminaPropertyMap.ChargeLimit,
            AminaPropertyMap.SinglePhase,
        ]


@unique
class AminaStatusMap(StrEnum):
    """Map Amina charger statuses to string representations."""

    Charging = "charging"
    ReadyToCharge = "ready_to_charge"


@unique
class AminaStateMap(StrEnum):
    """Map Amina charger states to string representations."""

    On = "ON"
    Off = "OFF"


# Hardware limits for Amina S
AMINA_HW_MAX_CURRENT = 32
AMINA_HW_MIN_CURRENT = 6


class AminaCharger(Zigbee2Mqtt, Charger):
    """Representation of an Amina S Charger using MQTT."""

    _LOGGER = logging.getLogger(__name__)

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        device: DeviceEntry,
    ) -> None:
        """Initialize the Amina Charger instance."""
        Zigbee2Mqtt.__init__(
            self,
            hass=hass,
            z2m_name=device.name,
            state_cache=dict.fromkeys([e.value for e in AminaPropertyMap], None),
            gettable_properties={e.value for e in AminaPropertyMap.gettable()},
        )
        Charger.__init__(self, hass=hass, config_entry=config_entry, device=device)

        # Track what we last commanded to handle hardware normalization
        self._last_commanded_limit: dict[Phase, int] | None = None

    @staticmethod
    def is_charger_device(device: DeviceEntry) -> bool:
        """Check if the given device is an Amina charger."""
        return any(
            (
                id_domain == HA_INTEGRATION_DOMAIN_MQTT
                and id_value.startswith(Z2M_DEVICE_IDENTIFIER_DOMAIN)
                and device.manufacturer == CHARGER_MANUFACTURER_AMINA
            )
            for id_domain, id_value in device.identifiers
        )

    async def async_setup(self) -> None:
        """Set up the Amina charger."""
        await self.async_setup_mqtt()

    async def set_phase_mode(
        self, mode: PhaseMode, _phase: Phase | None = None
    ) -> None:
        """Set the phase mode of the charger."""
        single_phase = "enable" if mode == PhaseMode.SINGLE else "disable"
        await self._async_mqtt_publish(
            topic=self._topic_set, payload={AminaPropertyMap.SinglePhase: single_phase}
        )

    async def set_current_limit(self, limit: dict[Phase, int]) -> None:
        """
        Set the charger limit and manage ON/OFF around the 6A hardware clamp.

        Hardware constraint: Amina cannot go below 6A when ON.
        Solution: Send OFF when below 6A, otherwise send ON + limit.
        """
        requested_current = min(limit.values()) if limit else 0

        # Store what we commanded for later normalization
        self._last_commanded_limit = dict(limit)

        # Below hardware minimum: turn OFF
        if requested_current < AMINA_HW_MIN_CURRENT:
            self._LOGGER.debug(
                "Requested %sA < %sA minimum, sending OFF + limit=%sA",
                requested_current,
                AMINA_HW_MIN_CURRENT,
                AMINA_HW_MIN_CURRENT,
            )
            await self._async_mqtt_publish(
                topic=self._topic_set,
                payload={
                    AminaPropertyMap.State: AminaStateMap.Off,
                    AminaPropertyMap.ChargeLimit: AMINA_HW_MIN_CURRENT,
                },
            )
            return

        # At or above minimum: send ON + actual limit
        current_value = min(requested_current, AMINA_HW_MAX_CURRENT)

        self._LOGGER.debug(
            "Requested %sA, sending ON + ChargeLimit=%sA",
            requested_current,
            current_value,
        )
        await self._async_mqtt_publish(
            topic=self._topic_set,
            payload={
                AminaPropertyMap.State: "ON",
                AminaPropertyMap.ChargeLimit: current_value,
            },
        )

    def get_current_limit(self) -> dict[Phase, int] | None:
        """
        Get the current charger limit in amps.

        Key behavior: When we commanded <6A (causing OFF state), we return what
        we commanded, not what hardware reports. This prevents false manual-override
        detection while still allowing real user changes to be detected.

        For values >=6A or when user manually changes something, return actual
        hardware state.
        """
        current_limit_val = self._state_cache.get(AminaPropertyMap.ChargeLimit)
        is_single_phase_val = self._state_cache.get(AminaPropertyMap.SinglePhase)
        state_val = self._state_cache.get(AminaPropertyMap.State)

        if current_limit_val is None or is_single_phase_val is None:
            return self._last_commanded_limit

        is_off = state_val is False or (
            isinstance(state_val, str) and str(state_val).upper() == AminaStateMap.Off
        )

        current_limit_int = int(current_limit_val)

        # Build what hardware is reporting
        if is_single_phase_val:
            hardware_limit = {Phase.L1: current_limit_int, Phase.L2: 0, Phase.L3: 0}
        else:
            hardware_limit = dict.fromkeys(Phase, current_limit_int)

        # If we have a last commanded limit, check if the OFF state is expected
        if self._last_commanded_limit is not None:
            commanded_min = min(self._last_commanded_limit.values())

            # If we commanded <6A and charger is OFF with 6A limit, return what we
            # commanded. This is the expected hardware behavior, not a manual override
            if (
                commanded_min < AMINA_HW_MIN_CURRENT
                and is_off
                and current_limit_int == AMINA_HW_MIN_CURRENT
            ):
                self._LOGGER.debug(
                    "Commanded %sA, charger OFF with 6A (expected), "
                    "returning commanded value",
                    commanded_min,
                )
                return dict(self._last_commanded_limit)

            # If we commanded >=6A, expect ON with that value
            # If hardware shows same value and is ON, return it
            if (
                commanded_min >= AMINA_HW_MIN_CURRENT
                and not is_off
                and all(
                    hardware_limit[p] == self._last_commanded_limit[p]
                    for p in hardware_limit
                )
            ):
                return dict(self._last_commanded_limit)

        # In all other cases, return actual hardware state
        # This allows manual overrides to be detected:
        # - User turns ON when we commanded OFF
        # - User changes limit when we're ON
        # - User turns OFF when we commanded ON
        if is_off:
            # Normalize OFF to 0 for consistency
            return dict.fromkeys(Phase, 0)

        return hardware_limit

    def get_max_current_limit(self) -> dict[Phase, int] | None:
        """Get the hardware maximum current limit of the charger."""
        return dict.fromkeys(Phase, AMINA_HW_MAX_CURRENT)

    def car_connected(self) -> bool:
        """Return whether the car is connected."""
        return bool(self._state_cache.get(AminaPropertyMap.EvConnected, False))

    def is_charging(self) -> bool:
        """Return whether the car is charging."""
        return bool(self._state_cache.get(AminaPropertyMap.Charging, False))

    def can_charge(self) -> bool:
        """Return if car is connected and accepting charge."""
        if not self.car_connected():
            return False

        ev_status = str(
            self._state_cache.get(AminaPropertyMap.EvStatus, "unknown")
        ).lower()

        return (
            ev_status in (AminaStatusMap.Charging, AminaStatusMap.ReadyToCharge)
            or "connected" in ev_status
        )

    def has_synced_phase_limits(self) -> bool:
        """Return whether the charger has synced phase limits."""
        return True

    async def async_unload(self) -> None:
        """Unload the Amina charger."""
        await self.async_unload_mqtt()
