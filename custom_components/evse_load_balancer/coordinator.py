import logging
from datetime import datetime, timedelta
from math import floor
from statistics import median
from time import time
from typing import Optional

from homeassistant.components.sensor import (
    SensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.util import Throttle

from . import config_flow as cf
from . import options_flow as of
from .chargers.charger import Charger
from .const import (
    COORDINATOR_STATE_AWAITING_CHARGER,
    COORDINATOR_STATE_MONITORING_LOAD,
    DOMAIN,
    EVENT_ACTION_NEW_CHARGER_LIMITS,
    EVENT_ATTR_ACTION,
    EVENT_ATTR_NEW_LIMITS,
    EVSE_LOAD_BALANCER_COORDINATOR_EVENT,
)
from .meters.meter import Meter, Phase

_LOGGER = logging.getLogger(__name__)

DEFAULT_THROTTLE_SECONDS = 5


class EVSELoadBalancerCoordinator:
    _hysteresis_buffer: dict[Phase, list[int]] = {phase: None for phase in Phase}
    _hysteresis_start: dict[Phase, Optional[int]] = {phase: None for phase in Phase}

    _last_check_timestamp: str = None

    def __init__(
        self,
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

        device_registry = dr.async_get(self.hass)
        self._device: DeviceEntry = device_registry.async_get_device(
            identifiers={(DOMAIN, self.config_entry.entry_id)}
        )

    async def async_setup(self) -> None:
        tracked_entities = self._meter.get_tracking_entities()
        _LOGGER.debug("Tracking entities: %s", tracked_entities)
        self._unsub.append(
            async_track_state_change_event(
                self.hass, tracked_entities, self._handle_meter_state_change
            )
        )
        self._unsub.append(
            self.config_entry.add_update_listener(self._handle_options_update)
        )

    async def async_unload(self) -> None:
        for unsub in self._unsub:
            unsub()
        self._unsub.clear()

    @callback
    def _handle_meter_state_change(self, event):
        self.hass.async_create_task(self._execute_update_cycle())

    async def _handle_options_update(self, hass: HomeAssistant, entry: ConfigEntry):
        await hass.config_entries.async_reload(entry.entry_id)

    def register_sensor(self, sensor: SensorEntity) -> None:
        self._sensors.append(sensor)

    def unregister_sensor(self, sensor: SensorEntity) -> None:
        self._sensors.remove(sensor)

    def get_available_current_for_phase(self, phase: Phase) -> Optional[int]:
        active_current = self._meter.get_active_phase_current(phase)
        return (
            max(0, min(self._fuse_size, floor(self.fuse_size - active_current)))
            if active_current is not None
            else None
        )

    def _get_available_currents(self) -> Optional[dict[Phase, int]]:
        """Check all phases and return the available current."""
        available_currents = {
            phase: self.get_available_current_for_phase(phase) for phase in Phase
        }
        if None in available_currents.values():
            _LOGGER.error(
                f"One of the available currents is None: {available_currents}."
            )
            return None
        return available_currents

    @property
    def fuse_size(self) -> float:
        return self.config_entry.data.get(cf.CONF_FUSE_SIZE, 0)

    @property
    def get_load_balancing_state(self) -> str:
        """Get the load balancing state."""
        if self._should_check_charger():
            return COORDINATOR_STATE_MONITORING_LOAD
        else:
            return COORDINATOR_STATE_AWAITING_CHARGER

    @property
    def get_last_check_timestamp(self) -> str:
        """Get the last check timestamp."""
        return self._last_check_timestamp

    @Throttle(timedelta(seconds=DEFAULT_THROTTLE_SECONDS))
    async def _execute_update_cycle(self):
        self._last_check_timestamp = datetime.now().astimezone()
        available_currents = self._get_available_currents()
        current_charger_setting = self._charger.get_current_limit()

        if available_currents is None:
            _LOGGER.warning("Available current unknown. Cannot adjust limit.")
            return

        if current_charger_setting is None:
            _LOGGER.warning(
                "Current charger current limit is not available. Cannot adjust limit."
            )
            return

        _LOGGER.debug(
            "Charger current available: %s, charger: %s",
            available_currents,
            current_charger_setting,
        )

        # making data available to sensors
        self._async_update_sensors()

        # Run the actual charger update
        if self._should_check_charger():
            new_charger_settings = current_charger_setting.copy()
            values_changed = False
            for phase, available_current in available_currents.items():
                charger_current = current_charger_setting.get(phase)
                if available_current < charger_current:
                    new_charger_settings[phase] = available_currents[phase]
                    values_changed = True
                elif available_current > charger_current:
                    new_current = self._apply_phase_hysteresis(phase, available_current)
                    if new_current is not None:
                        new_charger_settings[phase] = new_current
                        values_changed = True

            # Update the charger with the new settings
            if values_changed:
                _LOGGER.debug("New charger settings: %s", new_charger_settings)
                self._emit_charger_event(
                    EVENT_ACTION_NEW_CHARGER_LIMITS, new_charger_settings
                )
                await self._charger.set_current_limit(new_charger_settings)

    def _async_update_sensors(self):
        """Update all sensors"""
        for sensor in self._sensors:
            if sensor.enabled:
                sensor.async_write_ha_state()

    def _should_check_charger(self) -> bool:
        """Check if the charger should be checked for current limit changes."""
        return self._charger.is_charging()

    def _apply_phase_hysteresis(
        self, phase: Phase, available_current: int
    ) -> Optional[int]:
        now = int(time())
        if self._hysteresis_start[phase] is None:
            self._hysteresis_start[phase] = now
            self._hysteresis_buffer[phase] = []

        buffer = self._hysteresis_buffer[phase]
        start_time = self._hysteresis_start[phase]

        buffer.append(available_current)
        elapsed_min = (now - start_time) / 60

        if elapsed_min >= of.EvseLoadBalancerOptionsFlow.get_option_value(
            self.config_entry, of.OPTION_CHARGE_LIMIT_HYSTERESIS
        ):
            smoothened_current = int(median(self._hysteresis_buffer[phase]))
            self._reset_hysteresis(phase)
            return smoothened_current

        return None

    def _reset_hysteresis(self, phase: Phase):
        self._hysteresis_start[phase] = None
        self._hysteresis_buffer[phase].clear()

    def _emit_charger_event(self, action: str, new_limits: dict[Phase, int]) -> None:
        """Emit an event to Home Assistant's device event log."""
        self.hass.bus.async_fire(
            EVSE_LOAD_BALANCER_COORDINATOR_EVENT,
            {
                ATTR_DEVICE_ID: self._device.id,
                EVENT_ATTR_ACTION: action,
                EVENT_ATTR_NEW_LIMITS: new_limits,
            },
        )
        _LOGGER.info(
            "Emitted charger event: action=%s, new_limits=%s", action, new_limits
        )
