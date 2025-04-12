import logging
from typing import Optional
from homeassistant.helpers.device_registry import (
    DeviceEntry,
)
from homeassistant.helpers.entity_registry import (
    RegistryEntry
)
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.core import HomeAssistant
from .meter import (Meter, Phase)
from .. import config_flow as cf

_LOGGER = logging.getLogger(__name__)

# Mapping entities from the DSMR component based on their translation key
# @see https://github.com/home-assistant/core/blob/dev/homeassistant/components/dsmr/sensor.py
ENTITY_REGISTRATION_MAP: dict = {
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


class DsmrMeter(Meter):
    """
    DSMR Meter implementation of the Meter class.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        device_entry: DeviceEntry
    ):
        """
        Initialize the Meter instance.
        """
        self._hass = hass
        self.device_entry = device_entry
        self.entity_registry = er.async_get(self._hass)
        self.refresh_entities()

    def get_active_phase_current(self, phase: Phase) -> Optional[float]:
        """
        Returns the active current on a given phase
        """
        active_power = self.get_active_phase_power(phase)
        voltage_state = self._get_entity_state(phase, cf.CONF_PHASE_SENSOR_VOLTAGE)

        if None in [active_power, voltage_state]:
            _LOGGER.warning("Missing states for one of phase %s: active_power: %s, voltage: %s. Is it enabled?",
                            phase, active_power, voltage_state)
            return None
        return active_power / voltage_state if voltage_state else None

    def get_active_phase_power(self, phase: Phase) -> Optional[float]:
        """
        Returns the active power on a given phase
        """
        consumption_state = self._get_entity_state(phase, cf.CONF_PHASE_SENSOR_CONSUMPTION)
        production_state = self._get_entity_state(phase, cf.CONF_PHASE_SENSOR_PRODUCTION)

        if None in [consumption_state, production_state]:
            _LOGGER.warning("Missing states for one of phase %s: consumption: %s, production: %s",
                            phase, consumption_state, production_state)
            return None
        return (consumption_state - production_state)

    def get_tracking_entities(self) -> list[str]:
        """
        Returns a list of entity IDs that should be tracked for this meter
        to function properly. 
        """
        # Grab each phase in ENTITY_REGISTRATION_MAP and get the values. Return
        # a flattened list of all the values.
        translation_keys = [entity for phase in ENTITY_REGISTRATION_MAP.values() for entity in phase.values()]
        return [e.entity_id for e in self.entities if e.translation_key in translation_keys]

    def refresh_entities(self) -> None:
        """
        Refresh local list of entity maps for the meter.
        """
        self._entities = self._get_entities_for_device()

    def _get_entity_id(self, phase: Phase, sensor_const: str) -> Optional[float]:
        """
        Get the state of the entity for a given phase and translation key.
        """
        entity_map = self._get_entity_map_for_phase(phase)
        entity_translation_key = entity_map[sensor_const]
        entity: Optional[RegistryEntry] = next((e for e in self.entities if e.translation_key == entity_translation_key), None)
        if entity is None:
            raise ValueError(f"Entity not found for phase {phase} and sensor {sensor_const}")
        if entity.disabled:
            _LOGGER.error(f"Entity {entity.entity_id} is disabled. Please enable it!")
        return entity.entity_id

    def _get_entity_state(self, phase: Phase, sensor_const: str) -> Optional[float]:
        """
        Get the state of the entity for a given phase and translation key.
        """
        entity_id = self._get_entity_id(phase, sensor_const)
        state = self._hass.states.get(entity_id)
        if state is None:
            _LOGGER.debug("State not found for entity %s", entity_id)
            return None
        try:
            return float(state.state)
        except ValueError:
            _LOGGER.warning("State for entity %s is not a float: %s", entity_id, state.state)
            return None

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

    def _get_entities_for_device(self):
        """
        Set the entities for the meter.
        """
        # Get the entities associated with the device
        self.entities = self.entity_registry.entities.get_entries_for_device_id(
            self.device_entry.id,
            include_disabled_entities=True,
        )
