"""Custom Meter leveraging existing sensors."""

import logging
from math import floor

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .. import config_flow as cf  # noqa: TID252
from .meter import Meter, Phase

_LOGGER = logging.getLogger(__name__)

PHASE_CONF_MAP: dict[Phase, str] = {
    Phase.L1: cf.CONF_PHASE_KEY_ONE,
    Phase.L2: cf.CONF_PHASE_KEY_TWO,
    Phase.L3: cf.CONF_PHASE_KEY_THREE,
}


class CustomMeter(Meter):
    """Customer Meter implementation of the Meter class."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the Custom Meter instance."""
        Meter.__init__(self, hass, config_entry)
        self._config_entry_data = config_entry.data
        self._unavailable_sensors: set[str] = set()

    def get_active_phase_current(self, phase: Phase) -> int | None:
        """Return available current on a given phase."""
        phase_config = self._config_entry_data.get(PHASE_CONF_MAP[phase], None)
        if phase_config is None:
            return None

        active_power = self.get_active_phase_power(phase)
        voltage_state = self._get_state(phase_config[cf.CONF_PHASE_SENSOR_VOLTAGE])
        if None in [active_power, voltage_state]:
            _LOGGER.warning(
                (
                    "Missing states for one of phase %s: active_power: %s,",
                    " voltage_state: %s. Are the entities enabled?",
                ),
                phase,
                active_power,
                voltage_state,
            )
            return None
        return floor((active_power * 1000) / voltage_state) if voltage_state else None

    def get_active_phase_power(self, phase: Phase) -> float | None:
        """Return the active power on a given phase."""
        phase_config = self._config_entry_data[PHASE_CONF_MAP[phase]]
        consumption = self._get_state(phase_config[cf.CONF_PHASE_SENSOR_CONSUMPTION])
        production = self._get_state(phase_config[cf.CONF_PHASE_SENSOR_PRODUCTION])
        if None in [consumption, production]:
            _LOGGER.warning(
                (
                    "Missing states for one of phase %s: consumption: %s, "
                    "production: %s. Are the entities enabled?"
                ),
                phase,
                consumption,
                production,
            )
            return None
        return consumption - production

    def get_tracking_entities(self) -> list[str]:
        """Return a list of entity IDs that should be tracked for this meter."""
        sensors = []
        for phase_cf in PHASE_CONF_MAP.values():
            for cf_sensor in [
                cf.CONF_PHASE_SENSOR_CONSUMPTION,
                cf.CONF_PHASE_SENSOR_PRODUCTION,
                cf.CONF_PHASE_SENSOR_VOLTAGE,
            ]:
                sensors.extend(self._config_entry_data[phase_cf][cf_sensor])
        return sensors

    def get_unavailable_sensors(self) -> list[str]:
        """Return a list of currently unavailable sensors."""
        return list(self._unavailable_sensors)

    def _get_state(self, entity_id: str) -> float | None:
        state = self.hass.states.get(entity_id)
        if state is None:
            _LOGGER.debug("State not found for entity %s", entity_id)
            self._unavailable_sensors.add(entity_id)
            return None

        state_value = state.state

        if state_value in ("unavailable", "unknown"):
            self._unavailable_sensors.add(entity_id)
            return None

        try:
            value = float(state_value)
        except ValueError as ex:
            _LOGGER.exception(
                "Failed to parse state %s for entity %s: %s",
                state_value,
                entity_id,
                ex,  # noqa: TRY401
            )
            self._unavailable_sensors.add(entity_id)
            return None
        else:
            self._unavailable_sensors.discard(entity_id)
            return value
