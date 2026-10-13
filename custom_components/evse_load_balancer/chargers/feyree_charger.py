"""Feyree 22kW 3phase via Tuya Local's feyree_ev_portable_charger profile."""

import asyncio
from math import ceil, floor

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceEntry

from ..const import (  # noqa: TID252
    CONF_CHARGER_MAX_CURRENT,
    FEYREE_MANUFACTURER,
    FEYREE_MODEL,
    Phase,
)
from ..tuya_local_device import (  # noqa: TID252
    TuyaLocalDevice,
    finite_number,
    is_tuya_local_device,
)
from .charger import Charger, PhaseMode


class FeyreeCharger(Charger, TuyaLocalDevice):
    """Manage a common current limit and pause below the supported minimum."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
    ) -> None:
        """Resolve the supported profile's number, select and status entities."""
        Charger.__init__(self, hass, config_entry, device_entry)
        TuyaLocalDevice.__init__(self, hass, device_entry)
        self._paused_by_balancer = False
        self._lock = asyncio.Lock()

    @staticmethod
    def is_charger_device(device: DeviceEntry) -> bool:
        """Match the tested Tuya Local profile only."""
        return is_tuya_local_device(device, FEYREE_MANUFACTURER, FEYREE_MODEL)

    async def async_setup(self) -> None:
        """Validate controls without changing the charger's state."""
        for config_id in (
            "number_set_charge_current",
            "select_charging",
            "sensor_status",
        ):
            self.entity_id(config_id)
        self._bounds()

    def _bounds(self) -> tuple[int, int]:
        """Read hardware bounds and apply the explicitly configured circuit limit."""
        attrs = self._get_entity_state_attrs(
            self.entity_id("number_set_charge_current")
        )
        cap = finite_number(self.config_entry.data.get(CONF_CHARGER_MAX_CURRENT))
        minimum = finite_number(attrs.get("min")) if attrs else None
        maximum = finite_number(attrs.get("max")) if attrs else None
        if minimum is None or maximum is None or cap is None:
            msg = "Feyree current bounds or charger circuit limit unavailable"
            raise HomeAssistantError(msg)
        low, high = ceil(minimum), floor(min(maximum, cap))
        if low < 1 or high < low:
            msg = "Feyree charger circuit limit is below the hardware minimum"
            raise HomeAssistantError(msg)
        return low, high

    def set_phase_mode(self, mode: PhaseMode, phase: Phase | None = None) -> None:
        """Reject software phase switching, which this profile does not expose."""
        raise NotImplementedError

    def has_synced_phase_limits(self) -> bool:
        """Apply the same limit to all phases."""
        return True

    def normalize_current_limit(self, limit: dict[Phase, int]) -> dict[Phase, int]:
        """Represent a below-minimum limit as a pause, including in the allocator."""
        low, high = self._bounds()
        requested = min(limit.values())
        value = 0 if requested < low else min(floor(requested), high)
        return dict.fromkeys(Phase, value)

    async def _pause(self) -> None:
        mode = self._get_entity_state(self.entity_id("select_charging"))
        if mode not in ("on", "on_demand") or not self.can_charge():
            return
        await self.hass.services.async_call(
            "select",
            "select_option",
            {"entity_id": self.entity_id("select_charging"), "option": "off"},
            blocking=True,
        )
        self._paused_by_balancer = True

    async def async_handle_meter_unavailable(self) -> dict[Phase, int] | None:
        """Pause when any meter phase is unavailable; never operate its breaker."""
        async with self._lock:
            await self._pause()
            return dict.fromkeys(Phase, 0) if self._paused_by_balancer else None

    @property
    def pauses_on_meter_unavailable(self) -> bool:
        """Pause this charger when any required meter reading is unavailable."""
        return True

    async def set_current_limit(self, limit: dict[Phase, int]) -> None:
        """Set current before resuming; preserve manual off and authorization."""
        async with self._lock:
            current = min(self.normalize_current_limit(limit).values())
            if current == 0:
                await self._pause()
                return
            if not self.can_charge():
                return
            await self.hass.services.async_call(
                "number",
                "set_value",
                {
                    "entity_id": self.entity_id("number_set_charge_current"),
                    "value": current,
                },
                blocking=True,
            )
            if self._paused_by_balancer:
                await self.hass.services.async_call(
                    "select",
                    "select_option",
                    {
                        "entity_id": self.entity_id("select_charging"),
                        # WaitOperation (on_demand) does not reopen charging
                        # after CloseCharging; recovery needs OpenCharging.
                        "option": "on",
                    },
                    blocking=True,
                )
                self._paused_by_balancer = False

    def get_current_limit(self) -> dict[Phase, int] | None:
        """Return zero during a balancer-owned pause, retaining the recovery target."""
        mode = self._get_entity_state(self.entity_id("select_charging"))
        if mode == "off":
            return dict.fromkeys(Phase, 0)
        if mode not in ("on", "on_demand"):
            return None
        value = finite_number(
            self._get_entity_state(self.entity_id("number_set_charge_current"))
        )
        if value is None or value < 0:
            return None
        # Return actual values, including a manual value above the circuit cap,
        # so the allocator can detect and reduce it rather than hide it.
        return dict.fromkeys(Phase, floor(value))

    def get_max_current_limit(self) -> dict[Phase, int]:
        """Return the smaller of hardware and circuit limits."""
        _, maximum = self._bounds()
        return dict.fromkeys(Phase, maximum)

    def get_new_session_current_limit(self) -> dict[Phase, int] | None:
        """Preserve the user's selected current across new sessions."""
        current = self.get_current_limit()
        return self.normalize_current_limit(current) if current else None

    def car_connected(self) -> bool:
        """Exclude absent vehicles, faults and unfulfilled authorization."""
        status = self._get_entity_state(self.entity_id("sensor_status"))
        if status == "available":
            self._paused_by_balancer = False
        return status in ("plugged_in", "charging", "waiting", "charged")

    def can_charge(self) -> bool:
        """Continue monitoring pauses owned by this balancer for recovery."""
        if not self.car_connected():
            return False
        status = self._get_entity_state(self.entity_id("sensor_status"))
        mode = self._get_entity_state(self.entity_id("select_charging"))
        return (status != "charged" or self._paused_by_balancer) and (
            mode in ("on", "on_demand") or (mode == "off" and self._paused_by_balancer)
        )

    def is_charging(self) -> bool:
        """Return the reported charging state."""
        return self._get_entity_state(self.entity_id("sensor_status")) == "charging"

    async def async_unload(self) -> None:
        """Keep a paused charger stopped across reloads; do not start charging."""
