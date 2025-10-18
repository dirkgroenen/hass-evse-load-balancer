"""Amina Charger implementation using direct MQTT communication."""

from enum import StrEnum, unique
from typing import Self

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant  # State might not be used directly here
from homeassistant.helpers.device_registry import DeviceEntry

from ..const import (  # noqa: TID252
    CHARGER_MANUFACTURER_AMINA,
    HA_INTEGRATION_DOMAIN_MQTT,
    Z2M_DEVICE_IDENTIFIER_DOMAIN,
    Phase,
)
from .charger import Charger, PhaseMode
from .util.zigbee2mqtt import (
    Zigbee2Mqtt,
)


@unique
class AminaPropertyMap(StrEnum):
    """
    Map Easee properties.

    @see https://www.zigbee2mqtt.io/devices/amina_S.html
    """

    ChargeLimit = "charge_limit"
    SinglePhase = "single_phase"
    EvConnected = "ev_connected"
    EvStatus = "ev_status"
    Charging = "charging"

    def gettable() -> set[Self]:
        """Define properties that can be fetched via a /get request."""
        return (
            AminaPropertyMap.ChargeLimit,
            AminaPropertyMap.SinglePhase,
        )


@unique
class AminaStatusMap(StrEnum):
    """
    Map Amina charger statuses to their respective string representations.

    @see https://www.zigbee2mqtt.io/devices/amina_S.html#ev-status-text
    """

    Charging = "charging"
    ReadyToCharge = "ready_to_charge"


# Hardware limits for Amina S
AMINA_HW_MAX_CURRENT = 32
AMINA_HW_MIN_CURRENT = 6


class AminaCharger(Zigbee2Mqtt, Charger):
    """Representation of an Amina S Charger using MQTT."""

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
        """Check if the given device is an Easee charger."""
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
        single_phase = "disable"
        if mode == PhaseMode.SINGLE:
            single_phase = "enable"

        await self._async_mqtt_publish(
            topic=self._topic_set, payload={AminaPropertyMap.SinglePhase: single_phase}
        )

    async def set_current_limit(self, limit: dict[Phase, int]) -> None:
        """Set the charger limit."""
        current_value = min(*limit.values(), AMINA_HW_MAX_CURRENT)
        await self._async_mqtt_publish(
            topic=self._topic_set, payload={AminaPropertyMap.ChargeLimit: current_value}
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

        return ev_status in (
            AminaStatusMap.Charging,
            AminaStatusMap.ReadyToCharge,
        )

    def has_synced_phase_limits(self) -> bool:
        """Return whether the charger has synced phase limits."""
        return True

    async def async_unload(self) -> None:
        """Unload the Amina charger."""
        await self.async_unload_mqtt()
