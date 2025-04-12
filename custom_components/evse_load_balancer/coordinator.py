from typing import Optional
from homeassistant.core import (
    HomeAssistant,
    CALLBACK_TYPE,
    callback
)
from .chargers.charger import Charger
from .meters.meter import Meter, Phase
import logging
from homeassistant.util import Throttle
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.config_entries import ConfigEntry
from datetime import timedelta
from homeassistant.components.sensor import (
    SensorEntity,
)
from . import config_flow as cf

_LOGGER = logging.getLogger(__name__)

DEFAULT_THROTTLE_SECONDS = 5


class EVSELoadBalancerCoordinator:
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
        # TODO: Make this an actual configurable option
        self._throttle_interval = timedelta(seconds=config_entry.options.get(cf.OPTION_THROTTLE_SECONDS, DEFAULT_THROTTLE_SECONDS))

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

    async def async_unload(self) -> None:
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()

    @callback
    def _handle_state_change(self, event):
        self.hass.async_create_task(self._execute_update_cycle())

    def register_sensor(self, sensor: SensorEntity) -> None:
        self._sensors.append(sensor)

    def unregister_sensor(self, sensor: SensorEntity) -> None:
        self._sensors.remove(sensor)

    def get_available_current_for_phase(self, phase: Phase) -> Optional[float]:
        active_current = self._meter.get_active_phase_current(phase)
        return round(self.fuse_size - active_current, 2) if active_current else None

    @property
    def fuse_size(self) -> float:
        return self.config_entry.data.get(cf.CONF_FUSE_SIZE, 0)

    @Throttle(timedelta(seconds=DEFAULT_THROTTLE_SECONDS))
    async def _execute_update_cycle(self):
        available_currents = [self.get_available_current_for_phase(phase) for phase in Phase]
        # TODO: deal with unexpected none value in available_currents as that
        # could produce a faulty charger setting
        if None in available_currents:
            _LOGGER.warning(f"One of the available currents is None: {available_currents}. Cannot adjust limit.")
            return
        max_available = min(available_currents)

        current_charger_setting = self._charger.get_current_limit()
        if current_charger_setting is None:
            _LOGGER.warn("Current charger current limit is not available. Cannot adjust limit.")
            return

        _LOGGER.debug("Used per phase: %s, max charger available: %s, charger: %s",
                      available_currents, max_available, current_charger_setting)

        # making data available to sensors
        for sensor in self._sensors:
            sensor.async_write_ha_state()

        if current_charger_setting > max_available:
            _LOGGER.info("Reducing charger current from %d to %d", current_charger_setting, max_available)
            self._charger.set_current_limit(max_available)
            self._emit_charger_event("decreased", current_charger_setting, max_available)
        elif current_charger_setting < max_available:
            _LOGGER.info("Increasing charger current from %d to %d", current_charger_setting, max_available)
            self._charger.set_current_limit(max_available)
            self._emit_charger_event("increased", current_charger_setting, max_available)
        else:
            _LOGGER.debug("No update needed, charger current is within limit")

    def _emit_charger_event(self, action: str, old_limit: int, new_limit: int) -> None:
        """Emit an event to Home Assistant's device event log."""
        self.hass.bus.async_fire(
            "evse_load_balancer_charger_event",
            {
                "device_id": self.config_entry.entry_id,
                "action": action,
                "old_limit": old_limit,
                "new_limit": new_limit,
            }
        )
        _LOGGER.info("Emitted charger event: action=%s, old_limit=%d, new_limit=%d", action, old_limit, new_limit)
