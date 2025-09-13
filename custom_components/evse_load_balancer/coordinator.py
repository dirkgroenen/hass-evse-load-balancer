"""Main coordinator for load balacer."""

import logging
from datetime import datetime, timedelta  # Ensure datetime is imported
from functools import cached_property
from math import floor
from time import time

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_DEVICE_ID
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval

from . import config_flow as cf
from . import options_flow as of
from .balancers.optimised_load_balancer import OptimisedLoadBalancer
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
from .power_allocator import PowerAllocator

_LOGGER = logging.getLogger(__name__)

# Number of seconds between each check cycle
EXECUTION_CYCLE_DELAY: int = 1

# Number of seconds between each charger update. This setting
# makes sure that the charger is not updated too frequently and
# allows a change of the charger's limit to actually take affect
MIN_CHARGER_UPDATE_DELAY: int = 30


class EVSELoadBalancerCoordinator:
    """Coordinator for the EVSE Load Balancer."""

    # MODIFIED: Store as datetime object or None
    _last_check_timestamp: datetime | None = None
    _last_charger_target_update: tuple[dict[Phase, int], int] | None = None

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        meter: Meter,
        charger: Charger,
    ) -> None:
        """Initialize the coordinator."""
        self.hass: HomeAssistant = hass
        self.config_entry: ConfigEntry = config_entry
        self._unsub: list[CALLBACK_TYPE] = []
        self._sensors: list[SensorEntity] = []

        self._meter: Meter = meter
        self._charger: Charger = charger

    async def async_setup(self) -> None:
        """Set up the coordinator and its managed components."""
        await self._charger.async_setup()

        self._unsub.append(
            async_track_time_interval(
                self.hass,
                self._execute_update_cycle,
                timedelta(seconds=EXECUTION_CYCLE_DELAY),
            )
        )
        self._unsub.append(
            self.config_entry.add_update_listener(self._handle_options_update)
        )

        max_limits = dict.fromkeys(self._available_phases, self.fuse_size)
        self._balancer_algo = OptimisedLoadBalancer(
            max_limits=max_limits,
        )

        self._power_allocator = PowerAllocator()
        self._power_allocator.add_charger(charger=self._charger)

    async def async_unload(self) -> None:
        """Unload the coordinator and its managed components."""
        await self._charger.async_unload()

        for unsub_method in self._unsub:
            unsub_method()
        self._unsub.clear()

    @cached_property
    def _device(self) -> dr.DeviceEntry:
        """Get the device entry for the coordinator."""
        device_registry = dr.async_get(self.hass)
        device = device_registry.async_get_device(
            identifiers={(DOMAIN, self.config_entry.entry_id)}
        )
        if device is None:
            msg = (
                "Device entry for EVSE Load Balancer not found. "
                "This should not happen, please report this issue."
            )
            raise RuntimeError(msg)
        return device

    async def _handle_options_update(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
    ) -> None:
        """Handle options update by reloading the config entry."""
        await hass.config_entries.async_reload(entry.entry_id)

    def register_sensor(self, sensor: SensorEntity) -> None:
        """Register a sensor to be updated by the coordinator."""
        if sensor not in self._sensors:
            self._sensors.append(sensor)

    def unregister_sensor(self, sensor: SensorEntity) -> None:
        """Unregister a sensor."""
        if sensor in self._sensors:
            self._sensors.remove(sensor)

    @property
    def fuse_size(self) -> int:
        """
        Get the effective fuse size for load balancing.

        Considers the main fuse size from initial setup (config_entry.data)
        and the optional override from the integration's options (config_entry.options).
        """
        config_fuse_amps = self.config_entry.data.get(cf.CONF_FUSE_SIZE, 0)
        options_fuse_amps = self.config_entry.options.get(
            of.OPTION_MAX_FUSE_LOAD_AMPS, None
        )

        return int(
            options_fuse_amps if options_fuse_amps is not None else config_fuse_amps
        )

    def get_available_current_for_phase(self, phase: Phase) -> int | None:
        """Get the available current for a given phase."""
        active_current = self._meter.get_active_phase_current(phase)
        return (
            min(self.fuse_size, floor(self.fuse_size - active_current))
            if active_current is not None
            else None
        )

    def _get_available_currents(self) -> dict[Phase, int] | None:
        """Check all phases and return the available current for each."""
        available_currents = {}
        for phase_obj in self._available_phases:
            current = self.get_available_current_for_phase(phase_obj)
            if current is None:
                _LOGGER.error(
                    "Available current for phase '%s' is None."
                    "Cannot proceed with balancing cycle.",
                    phase_obj.value,
                )
                return None
            available_currents[phase_obj] = current
        return available_currents

    @cached_property
    def _available_phases(self) -> list[Phase]:
        """Get the available phases based on the user's configuration (1 or 3 phase)."""
        # Assumes CONF_PHASE_COUNT is stored in config_entry.data
        phase_count = int(self.config_entry.data.get(cf.CONF_PHASE_COUNT, 3))
        return list(Phase)[:phase_count]

    @property
    def get_load_balancing_state(self) -> str:
        """Get the current load balancing state."""
        if self._should_check_charger():
            return COORDINATOR_STATE_MONITORING_LOAD
        return COORDINATOR_STATE_AWAITING_CHARGER

    @property
    def get_last_check_timestamp(self) -> datetime | None:
        """Get the timestamp of the last check cycle."""
        return self._last_check_timestamp

    @callback
    def _execute_update_cycle(self, now: datetime) -> None:
        """Execute the main update cycle for load balancing."""
        self._last_check_timestamp = datetime.now().astimezone()
        available_currents = self._get_available_currents()

        self._async_update_sensors()

        if available_currents is None:
            _LOGGER.warning("Available current unknown. Cannot adjust limit.")
            return

        # Run the actual charger update
        if not self._should_check_charger():
            return

        # Computes relative limit. Negative in case of overcurrent
        # and positive in case of availability
        computed_availability = self._balancer_algo.compute_availability(
            available_currents=available_currents,
            now=now.timestamp(),
        )

        allocation_results = self._power_allocator.update_allocation(
            available_currents=computed_availability
        )

        # Allocator has been build to support multiple chargers. Right now
        # the coordinator only supports one charger. So we need to
        # iterate over the allocation results and update the charger
        # with the results. Just a bit of prep for the future...
        allocation_result = allocation_results.get(self._charger.id, None)
        if allocation_result and self._may_update_charger_settings(allocation_result):
            self._update_charger_settings(allocation_result)
            self._power_allocator.update_applied_current(
                charger_id=self._charger.id,
                applied_current=allocation_result,
                timestamp=now.timestamp(),
            )

    def _async_update_sensors(self) -> None:
        """Update all registered sensor states."""
        for sensor in self._sensors:
            if sensor.enabled and sensor.hass:
                sensor.async_write_ha_state()

    def _should_check_charger(self) -> bool:
        """Check if the charger is in a state where its limit should be managed."""
        return self._power_allocator.should_monitor()

    def _may_update_charger_settings(self, new_settings: dict[Phase, int]) -> bool:
        """Check if the charger settings haven't been updated too recently."""
        if self._last_charger_target_update is None:
            return True

        last_charger_target, last_update_time = self._last_charger_target_update
        now = int(time())

        of_charger_delay_minutes = of.EvseLoadBalancerOptionsFlow.get_option_value(
            self.config_entry, of.OPTION_CHARGE_LIMIT_HYSTERESIS
        )

        # Allow immediate decreases for safety (overcurrent protection)
        if any(new_settings[p] < last_charger_target[p] for p in new_settings):
            _LOGGER.debug(
                "New charger settings are lower, apply immediately for safety. "
                "Last settings: %s, new settings: %s",
                last_charger_target,
                new_settings,
            )
            return True

        # For increases, require minimum delay
        if now - last_update_time <= MIN_CHARGER_UPDATE_DELAY:
            _LOGGER.debug(
                "Charger settings was updated too recently (minimum delay). "
                "Last update: %s, current time: %s. "
                "Minimum delay: %s seconds",
                last_update_time,
                now,
                MIN_CHARGER_UPDATE_DELAY,
            )
            return False

        # For increases, also require configured delay
        if now - last_update_time > (of_charger_delay_minutes * 60):
            return True

        _LOGGER.debug(
            "Charger settings was updated too recently (configured delay). "
            "Last update: %s, current time: %s. "
            "Configured delay: %s minutes",
            last_update_time,
            now,
            of_charger_delay_minutes,
        )
        return False

    def _update_charger_settings(self, new_limits: dict[Phase, int]) -> None:
        _LOGGER.debug("New charger settings: %s", new_limits)
        self._last_charger_target_update = (
            new_limits,
            int(time()),
        )
        self._emit_charger_event(EVENT_ACTION_NEW_CHARGER_LIMITS, new_limits)
        self.hass.async_create_task(self._charger.set_current_limit(new_limits))

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
