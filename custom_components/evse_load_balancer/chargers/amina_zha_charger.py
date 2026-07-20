"""Amina S Charger implementation using ZHA (Zigbee Home Automation)."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from ..const import (  # noqa: TID252
    CHARGER_DOMAIN_ZHA,
    CHARGER_MANUFACTURER_AMINA,
    Phase,
)
from ..ha_device import HaDevice  # noqa: TID252
from .amina_charger import AMINA_HW_MAX_CURRENT, AMINA_HW_MIN_CURRENT
from .charger import Charger, PhaseMode

_LOGGER = logging.getLogger(__name__)

# The quirk pins all charger-control clusters to endpoint 10. The standard ZHA
# OnOff switch (cluster 0x0006) therefore gets a unique_id ending in "-10-6".
# It carries no custom translation_key, so it's resolved by this suffix.
# @see https://github.com/attaxia/amina_s_zha_quirk
AMINA_ZHA_ENDPOINT = 10
AMINA_ZHA_ONOFF_CLUSTER_ID = 6
AMINA_ZHA_ONOFF_UNIQUE_ID_SUFFIX = f"-{AMINA_ZHA_ENDPOINT}-{AMINA_ZHA_ONOFF_CLUSTER_ID}"
SWITCH_DOMAIN = "switch"


class AminaZhaEntityMap:
    """
    Map Amina S entities (exposed by the ZHA quirk) to their translation keys.

    @see https://github.com/attaxia/amina_s_zha_quirk/blob/main/amina_s.py
    """

    ChargeLimit = "charge_limit"  # number (current_level), 6-32A
    MaxCurrentLimit = "hardware_current_limit"  # sensor (physical selector cap)
    EvStatus = "ev_status"  # text sensor
    EvConnected = "ev_connected"  # binary_sensor (plug detected)
    Charging = "charging"  # binary_sensor (power delivered)
    SinglePhase = "single_phase"  # switch (force single-phase charging)


class AminaZhaStatusMap:
    """
    Map Amina S ``ev_status`` text values to their lowercase representations.

    The quirk renders the EV-status bitmap as human-readable text, optionally
    suffixed with " (derated)", so these are matched as substrings.
    @see https://github.com/attaxia/amina_s_zha_quirk/blob/main/amina_s.py
    """

    NotConnected = "not connected"
    Charging = "charging"
    Paused = "paused"
    ReadyToCharge = "ready to charge"
    EvConnected = "ev connected"


class AminaZhaCharger(HaDevice, Charger):
    """Implementation of the Charger class for ZHA-connected Amina S chargers."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
    ) -> None:
        """Initialize the Amina S ZHA charger."""
        HaDevice.__init__(self, hass, device_entry)
        Charger.__init__(self, hass, config_entry, device_entry)
        # Tracks whether we paused the charger by switching it off (because a
        # sub-6A limit was requested). The hardware can't charge below 6A, so a
        # pause is modelled as "off"; this flag lets get_current_limit() report
        # 0A while paused without having to (unreliably) infer it from the
        # OnOff switch state.
        self._paused: bool = False
        self.refresh_entities()

    @staticmethod
    def is_charger_device(device: DeviceEntry) -> bool:
        """Check if the given device is a ZHA-connected Amina charger."""
        manufacturer = (device.manufacturer or "").lower()
        return (
            any(id_domain == CHARGER_DOMAIN_ZHA for id_domain, _ in device.identifiers)
            and manufacturer == CHARGER_MANUFACTURER_AMINA.lower()
        )

    async def async_setup(self) -> None:
        """Set up the charger."""

    def _get_onoff_switch_entity_id(self) -> str:
        """Resolve the standard ZHA OnOff switch entity for the charger."""
        entity = next(
            (
                e
                for e in self.entities
                if e.domain == SWITCH_DOMAIN
                and e.unique_id.endswith(AMINA_ZHA_ONOFF_UNIQUE_ID_SUFFIX)
            ),
            None,
        )
        if entity is None:
            msg = "Amina ZHA on/off switch entity not found"
            raise ValueError(msg)
        return entity.entity_id

    async def _async_set_switch(self, entity_id: str, *, on: bool) -> None:
        """Turn a switch entity on or off."""
        await self.hass.services.async_call(
            domain=SWITCH_DOMAIN,
            service="turn_on" if on else "turn_off",
            service_data={"entity_id": entity_id},
            blocking=True,
        )

    async def set_phase_mode(
        self, mode: PhaseMode, _phase: Phase | None = None
    ) -> None:
        """Set the phase mode of the charger."""
        if mode not in PhaseMode:
            msg = "Invalid mode. Must be 'single' or 'multi'."
            raise ValueError(msg)

        single_phase_entity_id = self._get_entity_id_by_translation_key(
            AminaZhaEntityMap.SinglePhase
        )
        await self._async_set_switch(
            single_phase_entity_id, on=mode == PhaseMode.SINGLE
        )

    async def set_current_limit(self, limit: dict[Phase, int]) -> None:
        """
        Set the charger limit and manage ON/OFF around the 6A hardware clamp.

        Hardware constraint: the Amina S cannot charge below 6A. To pause, the
        standard ZHA on/off switch is turned off; otherwise the charger is
        turned on and the ``charge_limit`` number is set to the requested value.
        """
        requested_current = min(limit.values()) if limit else 0

        # Below hardware minimum: pause by switching the charger off.
        if requested_current < AMINA_HW_MIN_CURRENT:
            _LOGGER.debug(
                "Requested %sA < %sA minimum, switching charger OFF",
                requested_current,
                AMINA_HW_MIN_CURRENT,
            )
            self._paused = True
            await self._async_set_switch(self._get_onoff_switch_entity_id(), on=False)
            return

        # At or above minimum: set the limit, then ensure the charger is ON.
        self._paused = False
        value = min(requested_current, AMINA_HW_MAX_CURRENT)
        charge_limit_entity_id = self._get_entity_id_by_translation_key(
            AminaZhaEntityMap.ChargeLimit
        )
        _LOGGER.debug("Requested %sA, setting charge_limit=%sA + ON", value, value)
        await self.hass.services.async_call(
            domain="number",
            service="set_value",
            service_data={"entity_id": charge_limit_entity_id, "value": value},
            blocking=True,
        )
        await self._async_set_switch(self._get_onoff_switch_entity_id(), on=True)

    def get_current_limit(self) -> dict[Phase, int] | None:
        """Get the current charger limit in amps per phase."""
        # While paused (we switched the charger off for a sub-6A request) the
        # charger draws nothing; report 0 so the balancer can ramp it back up
        # from a paused state once headroom returns.
        if self._paused:
            return dict.fromkeys(Phase, 0)

        limit_state = self._get_entity_state_by_translation_key(
            AminaZhaEntityMap.ChargeLimit
        )
        if limit_state is None:
            _LOGGER.warning("Amina ZHA charge_limit entity unavailable")
            return None
        limit = int(float(limit_state))

        # The Amina S has synced phase limits, so the balancer only compares
        # min() across phases. Report the limit uniformly on every phase: zeroing
        # the unused phases in single-phase mode would force min() to 0 and the
        # balancer would never detect a change, so it would never adjust the
        # charge limit.
        return dict.fromkeys(Phase, limit)

    def get_max_current_limit(self) -> dict[Phase, int] | None:
        """Get the hardware maximum current limit of the charger."""
        try:
            state = self._get_entity_state_by_translation_key(
                AminaZhaEntityMap.MaxCurrentLimit
            )
        except ValueError:
            state = None
        if state is None:
            return dict.fromkeys(Phase, AMINA_HW_MAX_CURRENT)
        return dict.fromkeys(Phase, int(float(state)))

    def has_synced_phase_limits(self) -> bool:
        """Return whether the charger has synced phase limits."""
        return True

    def _get_status(self) -> str | None:
        return self._get_entity_state_by_translation_key(AminaZhaEntityMap.EvStatus)

    def car_connected(self) -> bool:
        """Return whether the car is connected."""
        return (
            self._get_entity_state_by_translation_key(AminaZhaEntityMap.EvConnected)
            == STATE_ON
        )

    def is_charging(self) -> bool:
        """Return whether the car is actively charging."""
        return (
            self._get_entity_state_by_translation_key(AminaZhaEntityMap.Charging)
            == STATE_ON
        )

    def can_charge(self) -> bool:
        """Return if car is connected and accepting charge."""
        if not self.car_connected():
            return False

        status = (self._get_status() or "").lower()
        return any(
            token in status
            for token in (
                AminaZhaStatusMap.Charging,
                AminaZhaStatusMap.ReadyToCharge,
                AminaZhaStatusMap.EvConnected,
            )
        )

    async def async_unload(self) -> None:
        """Unload the Amina S ZHA charger."""
