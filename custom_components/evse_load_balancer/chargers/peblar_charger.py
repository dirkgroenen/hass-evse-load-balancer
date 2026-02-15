"""Peblar Charger implementation."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from ..const import CHARGER_DOMAIN_PEBLAR, Phase  # noqa: TID252
from ..ha_device import HaDevice  # noqa: TID252
from .charger import Charger, PhaseMode

_LOGGER = logging.getLogger(__name__)


class PeblarEntityMap:
    """Map Peblar entities by key suffix."""

    State = "cp_state"
    ChargeLimit = "charge_current_limit"
    Charge = "charge"
    ForceSinglePhase = "force_single_phase"


class PeblarStateMap:
    """Peblar charger state values."""

    Charging = "charging"
    Suspended = "suspended"
    NoEvConnected = "no_ev_connected"
    Error = "error"
    Fault = "fault"
    Invalid = "invalid"


class PeblarCharger(HaDevice, Charger):
    """Implementation of the Charger class for Peblar chargers."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
    ) -> None:
        """Initialize the Peblar charger."""
        HaDevice.__init__(self, hass, device_entry)
        Charger.__init__(self, hass, config_entry, device_entry)
        self.refresh_entities()

    @staticmethod
    def is_charger_device(device: DeviceEntry) -> bool:
        """Check if the given device is a Peblar charger."""
        return any(
            id_domain == CHARGER_DOMAIN_PEBLAR for id_domain, _ in device.identifiers
        )

    async def async_setup(self) -> None:
        """Set up the charger."""

    async def set_phase_mode(
        self, mode: PhaseMode, _phase: Phase | None = None
    ) -> None:
        """Set the phase mode of the charger when supported."""
        if not isinstance(mode, PhaseMode):
            msg = "Invalid mode. Must be 'single' or 'multi'."
            raise ValueError(msg)

        try:
            force_single_phase_entity_id = self._get_entity_id_by_key(
                PeblarEntityMap.ForceSinglePhase
            )
        except ValueError:
            _LOGGER.debug(
                "Peblar force_single_phase switch not found. Skipping phase mode update."
            )
            return

        service = "turn_on" if mode == PhaseMode.SINGLE else "turn_off"
        await self.hass.services.async_call(
            domain="switch",
            service=service,
            service_data={"entity_id": force_single_phase_entity_id},
            blocking=True,
        )

    def has_synced_phase_limits(self) -> bool:
        """Return whether the charger has synced phase limits."""
        return True

    async def set_current_limit(self, limit: dict[Phase, int]) -> None:
        """Set the current limit for the Peblar charger."""
        if not limit:
            _LOGGER.warning("No limit values provided for Peblar charger update.")
            return

        try:
            charge_limit_entity_id = self._get_entity_id_by_key(
                PeblarEntityMap.ChargeLimit
            )
            attrs = (
                self._get_entity_state_attrs_by_key(PeblarEntityMap.ChargeLimit) or {}
            )
        except ValueError:
            _LOGGER.warning(
                "Peblar charge current limit entity not found. Skipping limit update."
            )
            return

        requested_limit = min(limit.values())
        min_limit = self._parse_attr_limit(attrs.get("min"), fallback=6)
        max_limit = self._parse_attr_limit(attrs.get("max"), fallback=32)

        charge_entity_id = None
        try:
            charge_entity_id = self._get_entity_id_by_key(PeblarEntityMap.Charge)
        except ValueError:
            _LOGGER.warning("Peblar charge switch entity not found.")

        if requested_limit < min_limit:
            if charge_entity_id is None:
                _LOGGER.warning(
                    "Cannot disable Peblar charging without charge switch entity."
                )
                return
            await self.hass.services.async_call(
                domain="switch",
                service="turn_off",
                service_data={"entity_id": charge_entity_id},
                blocking=True,
            )
            return

        value = max(min_limit, min(requested_limit, max_limit))

        await self.hass.services.async_call(
            domain="number",
            service="set_value",
            service_data={
                "entity_id": charge_limit_entity_id,
                "value": value,
            },
            blocking=True,
        )

        if charge_entity_id is None:
            return

        charge_switch_on = self._get_charge_switch_state()
        if charge_switch_on is False:
            await self.hass.services.async_call(
                domain="switch",
                service="turn_on",
                service_data={"entity_id": charge_entity_id},
                blocking=True,
            )
        elif charge_switch_on is None:
            _LOGGER.debug(
                "Peblar charge switch state is unknown. Skipping automatic turn_on."
            )

    def get_current_limit(self) -> dict[Phase, int] | None:
        """Get the currently configured Peblar current limit in amps."""
        charge_switch_on = self._get_charge_switch_state()
        if charge_switch_on is False:
            return dict.fromkeys(Phase, 0)
        if charge_switch_on is None:
            return None

        try:
            state = self._get_entity_state_by_key(PeblarEntityMap.ChargeLimit)
        except ValueError:
            _LOGGER.warning("Peblar charge current limit entity not found.")
            return None
        if state is None:
            return None

        try:
            limit = int(float(state))
        except (ValueError, TypeError):
            _LOGGER.exception("Could not parse Peblar charge limit '%s'", state)
            return None

        return dict.fromkeys(Phase, limit)

    def get_max_current_limit(self) -> dict[Phase, int] | None:
        """Get the maximum configured Peblar current limit in amps."""
        try:
            attrs = self._get_entity_state_attrs_by_key(PeblarEntityMap.ChargeLimit)
        except ValueError:
            _LOGGER.warning("Peblar charge current limit entity not found.")
            return None
        if not attrs:
            return None

        max_current = attrs.get("max")
        if max_current is None:
            return None

        max_current_int = self._parse_attr_limit(max_current, fallback=None)
        if max_current_int is None:
            return None

        return dict.fromkeys(Phase, max_current_int)

    def _parse_attr_limit(
        self, value: str | float | int | None, fallback: int | None
    ) -> int | None:
        """Parse a numeric entity attribute used for current boundaries."""
        try:
            return int(float(value)) if value is not None else fallback
        except (ValueError, TypeError):
            _LOGGER.exception("Could not parse Peblar boundary attribute '%s'", value)
            return fallback

    def _get_state(self) -> str | None:
        try:
            state = self._get_entity_state_by_key(PeblarEntityMap.State)
        except ValueError:
            _LOGGER.warning("Peblar cp_state entity not found.")
            return None
        return str(state).lower() if state is not None else None

    def _get_charge_switch_state(self) -> bool | None:
        """Get Peblar charge switch state as True/False/None (unknown)."""
        try:
            switch_state = self._get_entity_state_by_key(PeblarEntityMap.Charge)
        except ValueError:
            _LOGGER.warning("Peblar charge switch entity not found.")
            return None
        if switch_state is None:
            _LOGGER.debug("Peblar charge switch state is unavailable.")
            return None

        return str(switch_state).lower() == "on"

    def car_connected(self) -> bool:
        """Return whether the car is physically connected to the charger."""
        state = self._get_state()
        return state is not None and state != PeblarStateMap.NoEvConnected

    def can_charge(self) -> bool:
        """Return whether the car is connected and charging is currently allowed."""
        state = self._get_state()
        if state is None or state == PeblarStateMap.NoEvConnected:
            return False

        return state not in (
            PeblarStateMap.Error,
            PeblarStateMap.Fault,
            PeblarStateMap.Invalid,
        )

    def is_charging(self) -> bool:
        """Return whether the charger is actively charging."""
        return self._get_state() == PeblarStateMap.Charging

    async def async_unload(self) -> None:
        """Unload the Peblar charger."""
