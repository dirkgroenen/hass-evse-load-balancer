from typing import Optional
from homeassistant.core import (
    HomeAssistant,
    CALLBACK_TYPE,
    callback
)
from math import floor
from statistics import median
from .chargers.charger import Charger
from .meters.meter import Meter, Phase
import logging
from homeassistant.util import Throttle
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.config_entries import ConfigEntry
from datetime import timedelta
from time import time
from homeassistant.components.sensor import (
    SensorEntity,
)
from . import config_flow as cf, options_flow as of

_LOGGER = logging.getLogger(__name__)

DEFAULT_THROTTLE_SECONDS = 5


class EVSELoadBalancerCoordinator:
    _hysteresis_buffer: list[int] = []
    _hysteresis_start: Optional[int] = None

    def __init__(self,
                 hass: HomeAssistant,
                 config_entry: ConfigEntry,
                 meter: Meter,
                 charger: Charger,
                 ) -> None:
        self.hass: HomeAssistant = hass
        self.config_entry: ConfigEntry = config_entry

        self._unsub: list[CALLBACK_TYPE] = []
        self._sensors: list[SensorEntity] = []

        self._fuse_size = config_entry.data.get(cf.CONF_FUSE_SIZE, 0)

        self._meter: Meter = meter
        self._charger: Charger = charger

    async def async_setup(self) -> None:
        tracked_entities = self._meter.get_tracking_entities()
        _LOGGER.debug("Tracking entities: %s", tracked_entities)
        self._unsub.append(
            async_track_state_change_event(
                self.hass, tracked_entities, self._handle_state_change
            )
        )
        self._unsub.append(
            self.config_entry.add_update_listener(
                self._handle_options_update
            )
        )

    async def async_unload(self) -> None:
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()

    @callback
    def _handle_state_change(self, event):
        self.hass.async_create_task(self._execute_update_cycle())

    async def _handle_options_update(self, hass: HomeAssistant, entry: ConfigEntry):
        await hass.config_entries.async_reload(entry.entry_id)

    def register_sensor(self, sensor: SensorEntity) -> None:
        self._sensors.append(sensor)

    def unregister_sensor(self, sensor: SensorEntity) -> None:
        self._sensors.remove(sensor)

    def get_available_current_for_phase(self, phase: Phase) -> Optional[int]:
        active_current = self._meter.get_active_phase_current(phase)
        return min(self._fuse_size, floor(self.fuse_size - active_current)) if active_current else None

    @property
    def fuse_size(self) -> float:
        return self.config_entry.data.get(cf.CONF_FUSE_SIZE, 0)

    @Throttle(timedelta(seconds=DEFAULT_THROTTLE_SECONDS))
    async def _execute_update_cycle(self):
        available_current = self._get_available_current()
        current_charger_setting = self._charger.get_current_limit()

        if available_current is None:
            _LOGGER.warning("Available current unknown. Cannot adjust limit.")
            return

        if current_charger_setting is None:
            _LOGGER.warning("Current charger current limit is not available. Cannot adjust limit.")
            return

        _LOGGER.debug("Charger current available: %s, charger: %s", available_current, current_charger_setting)

        # making data available to sensors
        self._async_update_sensors()

        # Run the actual charger update
        if self._should_check_charger():
            if available_current < current_charger_setting:
                await self._charger_limit_decrease(self._charger, available_current)
            elif available_current > current_charger_setting:
                await self._attempt_charger_limit_increase(self._charger, available_current)
            else:
                _LOGGER.debug("No update needed, charger current is within limit")

    def _get_available_current(self) -> Optional[int]:
        """Check all phases and return the minimum available current."""
        available_currents = [self.get_available_current_for_phase(phase) for phase in Phase]
        # TODO: deal with unexpected none value in available_currents as that
        # could produce a faulty charger setting
        if None in available_currents:
            _LOGGER.warning(f"One of the available currents is None: {available_currents}.")
            return
        return min(available_currents)

    def _async_update_sensors(self):
        """Update all sensors"""
        for sensor in self._sensors:
            if sensor.enabled:
                sensor.async_write_ha_state()

    def _should_check_charger(self) -> bool:
        """Check if the charger should be checked for current limit changes."""
        return self._charger.is_charging()

    async def _charger_limit_decrease(self, charger: Charger, current: int):
        _LOGGER.info("Setting charger current to %d", current)
        await charger.set_current_limit(current)
        self._emit_charger_event("decreased", current)

    async def _attempt_charger_limit_increase(self, charger: Charger, available_current: int):
        now = int(time())
        if self._hysteresis_start is None:
            self._hysteresis_start = now
            self._hysteresis_buffer = [available_current]
            _LOGGER.debug("Hysteresis started at %s", self._hysteresis_start)
        else:
            self._hysteresis_buffer.append(available_current)
            elapsed_min = (now - self._hysteresis_start) / 60

            if elapsed_min >= of.EvseLoadBalancerOptionsFlow.get_option_value(self.config_entry, of.OPTION_CHARGE_LIMIT_HYSTERESIS):
                smoothened_current = int(median(self._hysteresis_buffer))
                _LOGGER.info("Hysteresis complete. Setting charger current to median: %d A", smoothened_current)
                await charger.set_current_limit(smoothened_current)
                self._emit_charger_event("increased", smoothened_current)
                self._reset_hysteresis()

    def _reset_hysteresis(self):
        self._hysteresis_start = None
        self._hysteresis_buffer.clear()

    def _emit_charger_event(self, action: str, new_limit: int) -> None:
        """Emit an event to Home Assistant's device event log."""
        self.hass.bus.async_fire(
            "evse_load_balancer_charger_event",
            {
                "device_id": self.config_entry.entry_id,
                "action": action,
                "new_limit": new_limit,
            }
        )
        _LOGGER.info("Emitted charger event: action=%s, new_limit=%d", action, new_limit)
