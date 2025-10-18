"""Amina Charger implementation using direct MQTT communication."""

import logging
from enum import StrEnum, unique
from typing import Self

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

    def gettable() -> list[Self]:
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
            gettable_properties=[e.value for e in AminaPropertyMap.gettable()],
        )
        Charger.__init__(self, hass=hass, config_entry=config_entry, device=device)

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

        For synced chargers like Amina, use the minimum across phases
        (the charger applies the same limit to all phases). Tests and
        behavior expect the smallest per-phase requested value to be used.
        """
        requested_current = min(limit.values()) if limit else 0

        # Pause path: explicitly turn the charger OFF when we request below HW min
        if requested_current < AMINA_HW_MIN_CURRENT:
            self._LOGGER.debug(
                "AminaCharger: requested %sA < %sA, sending OFF + charge_limit=%s",
                requested_current,
                AMINA_HW_MIN_CURRENT,
                AMINA_HW_MIN_CURRENT,
            )
            await self._async_mqtt_publish(
                topic=self._topic_set,
                payload={
                    AminaPropertyMap.State: "OFF",
                    AminaPropertyMap.ChargeLimit: AMINA_HW_MIN_CURRENT,
                },
            )
            return

        # Enable path: request >= AMINA_HW_MIN_CURRENT
        current_value = min(requested_current, AMINA_HW_MAX_CURRENT)
        car_conn = self.car_connected()
        ev_status = self._state_cache.get(AminaPropertyMap.EvStatus)

        self._LOGGER.debug(
            "AminaCharger: car_connected=%s ev_status=%s requested=%s",
            car_conn,
            ev_status,
            requested_current,
        )

        if not car_conn:
            # Car not connected — just publish limit
            self._LOGGER.debug(
                "AminaCharger: car not connected; publishing ChargeLimit only "
                "(requested=%s)",
                requested_current,
            )
            await self._async_mqtt_publish(
                topic=self._topic_set,
                payload={AminaPropertyMap.ChargeLimit: current_value},
            )
            return

        # Car connected — send ON + ChargeLimit
        self._LOGGER.debug(
            "AminaCharger: publishing ON and ChargeLimit=%s",
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
        """Get the current charger limit in amps from internal cache."""
        current_limit_val = self._state_cache.get(AminaPropertyMap.ChargeLimit)
        is_single_phase_val = self._state_cache.get(AminaPropertyMap.SinglePhase)

        if current_limit_val is None or is_single_phase_val is None:
            return None

        current_limit_int = int(current_limit_val)

        if is_single_phase_val:
            return {Phase.L1: current_limit_int, Phase.L2: 0, Phase.L3: 0}
        return dict.fromkeys(Phase, current_limit_int)

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

        # Some firmware reports 'EV Connected' or similar when the vehicle is
        # physically connected but not yet 'ready_to_charge'. Treat a
        # connected vehicle as charge-capable so the coordinator/allocator
        # will continue to monitor and attempt to enable the charger by
        # sending State=ON.
        return (
            ev_status in (AminaStatusMap.Charging, AminaStatusMap.ReadyToCharge)
            or "connected" in ev_status
        )

    def has_synced_phase_limits(self) -> bool:
        """Return whether the charger has synced phase limits."""
        return True

    def acknowledge_hardware_override(
        self,
        reported_limit: dict[Phase, int] | None,
        last_applied: dict[Phase, int] | None,
    ) -> bool:
        """
        Amina hardware clamp suppression.

        Amina hardware clamps requests below AMINA_HW_MIN_CURRENT to
        AMINA_HW_MIN_CURRENT when the device is turned OFF.

        If we have recently applied a request below the HW min and the
        device reports the clamped value while in OFF state, treat this
        as a hardware-driven clamp and not a user manual override.
        """
        if not reported_limit or not last_applied:
            return False

        if (
            all(v == AMINA_HW_MIN_CURRENT for v in reported_limit.values())
            and any(v < AMINA_HW_MIN_CURRENT for v in last_applied.values())
        ):
            state_val = self._state_cache.get(AminaPropertyMap.State)
            if state_val is False:
                return True
            if isinstance(state_val, str) and str(state_val).upper() == "OFF":
                return True

        return False

    async def async_unload(self) -> None:
        """Unload the Amina charger."""
        await self.async_unload_mqtt()
