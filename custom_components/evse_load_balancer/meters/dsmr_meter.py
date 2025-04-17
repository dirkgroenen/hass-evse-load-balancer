import logging
from typing import Optional
from homeassistant.helpers.device_registry import (
    DeviceEntry,
)
from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry

from ..ha_device import HaDevice
from .meter import (Meter, Phase)
from .. import config_flow as cf
from math import floor

_LOGGER = logging.getLogger(__name__)

# Mapping entities from the DSMR component based on their translation key
# @see https://github.com/home-assistant/core/blob/dev/homeassistant/components/dsmr/sensor.py
ENTITY_REGISTRATION_MAP: dict[str, dict[str, str]] = {
    cf.CONF_PHASE_KEY_ONE: {
        cf.CONF_PHASE_SENSOR_PRODUCTION: 'instantaneous_active_power_l1_negative',
        cf.CONF_PHASE_SENSOR_CONSUMPTION: 'instantaneous_active_power_l1_positive',
        cf.CONF_PHASE_SENSOR_VOLTAGE: 'instantaneous_voltage_l1',
    },
    cf.CONF_PHASE_KEY_TWO: {
        cf.CONF_PHASE_SENSOR_PRODUCTION: 'instantaneous_active_power_l2_negative',
        cf.CONF_PHASE_SENSOR_CONSUMPTION: 'instantaneous_active_power_l2_positive',
        cf.CONF_PHASE_SENSOR_VOLTAGE: 'instantaneous_voltage_l2',
    },
    cf.CONF_PHASE_KEY_THREE: {
        cf.CONF_PHASE_SENSOR_PRODUCTION: 'instantaneous_active_power_l3_negative',
        cf.CONF_PHASE_SENSOR_CONSUMPTION: 'instantaneous_active_power_l3_positive',
        cf.CONF_PHASE_SENSOR_VOLTAGE: 'instantaneous_voltage_l3',
    }
}


class DsmrMeter(Meter, HaDevice):
    """
    DSMR Meter implementation of the Meter class.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        device_entry: DeviceEntry
    ):
        """
        Initialize the Meter instance.
        """
        Meter.__init__(self, hass, config_entry)
        HaDevice.__init__(self, hass, device_entry)
        self.refresh_entities()

    def get_active_phase_current(self, phase: Phase) -> Optional[int]:
        """
        Returns the active current on a given phase
        """
        active_power = self.get_active_phase_power(phase)
        voltage_state = self._get_entity_state_for_phase_sensor(phase, cf.CONF_PHASE_SENSOR_VOLTAGE)

        if None in [active_power, voltage_state]:
            _LOGGER.warning("Missing states for one of phase %s: active_power: %s, voltage: %s. Is it enabled?",
                            phase, active_power, voltage_state)
            return None
        # convert kW to W in order to calculate the current
        return floor((active_power * 1000) / voltage_state) if voltage_state else None

    def get_active_phase_power(self, phase: Phase) -> Optional[float]:
        """
        Returns the active power on a given phase. 
        """
        consumption_state = self._get_entity_state_for_phase_sensor(phase, cf.CONF_PHASE_SENSOR_CONSUMPTION)
        production_state = self._get_entity_state_for_phase_sensor(phase, cf.CONF_PHASE_SENSOR_PRODUCTION)

        if None in [consumption_state, production_state]:
            _LOGGER.warning("Missing states for one of phase %s: consumption: %s, production: %s",
                            phase, consumption_state, production_state)
            return None
        return (production_state - consumption_state)

    def get_tracking_entities(self) -> list[str]:
        """
        Returns a list of entity IDs that should be tracked for this meter
        to function properly.
        """
        # Grab each phase in ENTITY_REGISTRATION_MAP and get the values. Return
        # a flattened list of all the values.
        translation_keys = [entity for phase in ENTITY_REGISTRATION_MAP.values() for entity in phase.values()]
        return [e.entity_id for e in self.entities if e.translation_key in translation_keys]

    def _get_entity_id_for_phase_sensor(self, phase: Phase, sensor_const: str) -> Optional[float]:
        """
        Get the state of the entity for a given phase and translation key.
        """
        return self._get_entity_id_by_translation_key(
            self._get_entity_map_for_phase(phase)[sensor_const]
        )

    def _get_entity_state_for_phase_sensor(self, phase: Phase, sensor_const: str) -> Optional[float]:
        """
        Get the state of the entity for a given phase and translation key.
        """
        entity_id = self._get_entity_id_for_phase_sensor(phase, sensor_const)
        return self._get_entity_state(entity_id, float)

    def _get_entity_map_for_phase(self, phase: Phase) -> dict:
        entity_map = {}
        if phase == Phase.L1:
            entity_map = ENTITY_REGISTRATION_MAP[cf.CONF_PHASE_KEY_ONE]
        elif phase == Phase.L2:
            entity_map = ENTITY_REGISTRATION_MAP[cf.CONF_PHASE_KEY_TWO]
        elif phase == Phase.L3:
            entity_map = ENTITY_REGISTRATION_MAP[cf.CONF_PHASE_KEY_THREE]
        else:
            raise ValueError(f"Invalid phase: {phase}")
        return entity_map
