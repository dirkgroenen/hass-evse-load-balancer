"""AMSHAN Meter implementation."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .. import config_flow as cf
from .. import options_flow as of
from ..ha_device import HaDevice
from .meter import Meter, Phase

_LOGGER = logging.getLogger(__name__)

# Mapping entities from the DSMR component based on their translation key
# @see https://github.com/toreamun/amshan-homeassistant/blob/master/custom_components/amshan/sensor.py
ENTITY_REGISTRATION_MAP = {
    cf.CONF_PHASE_KEY_ONE: {
        cf.CONF_PHASE_SENSOR_CURRENT: "current_l1",
        cf.CONF_PHASE_SENSOR_VOLTAGE: "voltage_l1",
        cf.CONF_PHASE_SENSOR_CONSUMPTION: "active_power_import_l1",
        cf.CONF_PHASE_SENSOR_PRODUCTION: "active_power_export_l1",
    },
    cf.CONF_PHASE_KEY_TWO: {
        cf.CONF_PHASE_SENSOR_CURRENT: "current_l2",
        cf.CONF_PHASE_SENSOR_VOLTAGE: "voltage_l2",
        cf.CONF_PHASE_SENSOR_CONSUMPTION: "active_power_import_l2",
        cf.CONF_PHASE_SENSOR_PRODUCTION: "active_power_export_l2",
    },
    cf.CONF_PHASE_KEY_THREE: {
        cf.CONF_PHASE_SENSOR_CURRENT: "current_l3",
        cf.CONF_PHASE_SENSOR_VOLTAGE: "voltage_l3",
        cf.CONF_PHASE_SENSOR_CONSUMPTION: "active_power_import_l3",
        cf.CONF_PHASE_SENSOR_PRODUCTION: "active_power_export_l3",
    },
}


class AmshanMeter(Meter, HaDevice):
    """AMS HAN Meter implementation of the Meter class."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
    ) -> None:
        """Initialize the Meter instance."""
        Meter.__init__(self, hass, config_entry)
        HaDevice.__init__(self, hass, device_entry)
        self.device_entry = device_entry
        self.refresh_entities()

        # Find a valid sensor entity and extract the prefix
        self._entity_prefix = None
        map_values = {
            v
            for phase_map in ENTITY_REGISTRATION_MAP.values()
            for v in phase_map.values()
        }
        for e in self.entities:
            if e.entity_id.startswith("sensor."):
                entity_id_no_domain = e.entity_id[len("sensor.") :]

                for map_value in map_values:
                    if entity_id_no_domain.endswith(map_value):
                        # Remove the map_value from the end to get the prefix (may include underscores)
                        prefix = entity_id_no_domain[: -len(map_value)]
                        self._entity_prefix = prefix
                        _LOGGER.debug(
                            "Detected AMSHAN entity prefix: '%s'", self._entity_prefix
                        )
                        break
                if self._entity_prefix:
                    break
        if not self._entity_prefix:
            raise RuntimeError("Could not determine AMSHAN entity prefix.")

    def _get_entity_id_by_translation_key(self, entity_translation_key: str) -> str:
        """Build entity_id using detected prefix and translation key."""
        entity_id = f"sensor.{self._entity_prefix}{entity_translation_key}"
        if not any(e.entity_id == entity_id for e in self.entities):
            raise ValueError(f"Entity {entity_id} not found for AMSHAN meter.")
        return entity_id

    def get_active_phase_current(self, phase: Phase) -> int | None:
        """Return the active current on a given phase."""
        current_state = self._get_entity_state_for_phase_sensor(
            phase, cf.CONF_PHASE_SENSOR_CURRENT
        )

        if current_state is None:
            _LOGGER.debug(
                (
                    "Missing state for current phase %s: %s, ",
                    "Is the entitiy enabled?",
                ),
                phase.value,
                current_state,
            )
            return None
        # convert to int
        raw_value = current_state
        return round(raw_value)

    def get_active_phase_power(self, phase: Phase) -> float | None:
        """Return active power on the requested phase (watts) or None.

        Priority:
        1) If AMSHAN provides per-phase consumption/production => compute net (cons - prod)
        2) Else if voltage + current sensors present => P = V * I
        3) Else None

        AMSHAN exposes import/export total but not per phase power (yet, at least),
        so we can approximate per phase power by:
        P_phase = (Voltage_phase * Current_phase) if both exist
        """

        # 1) Try dedicated power sensors (consumption/production)
        consumption_state = self._get_entity_state_for_phase_sensor(
            phase, cf.CONF_PHASE_SENSOR_CONSUMPTION
        )
        production_state = self._get_entity_state_for_phase_sensor(
            phase, cf.CONF_PHASE_SENSOR_PRODUCTION
        )

        if not None in [consumption_state, production_state]:
            return consumption_state - production_state

        _LOGGER.warning(
            "Missing states for one of phase %s: consumption: %s, production: %s",
            phase,
            consumption_state,
            production_state,
        )

        # 2) Fallback: phase voltage * phase current
        v = self._get_entity_state_for_phase_sensor(phase, cf.CONF_PHASE_SENSOR_VOLTAGE)
        i = self._get_entity_state_for_phase_sensor(phase, cf.CONF_PHASE_SENSOR_CURRENT)

        if v is not None and i is not None:
            return v * i

        # 3) No per-phase power possible
        _LOGGER.warning(
            f"Cannot determine active power for phase {phase.value}. "
            "No consumption/production sensors or voltage/current sensors available."
        )
        return None

    def get_tracking_entities(self) -> list[str]:
        """Return a list of entity IDs that should be tracked for this meter."""
        # Grab each phase in ENTITY_REGISTRATION_MAP and get the values. Return
        # a flattened list of all the values.
        translation_keys = [
            entity
            for phase in ENTITY_REGISTRATION_MAP.values()
            for entity in phase.values()
        ]
        return [
            e.entity_id for e in self.entities if e.translation_key in translation_keys
        ]

    def _get_entity_id_for_phase_sensor(
        self, phase: Phase, sensor_const: str
    ) -> float | None:
        """Get the state of the entity for a given phase and translation key."""
        return self._get_entity_id_by_translation_key(
            self._get_entity_map_for_phase(phase)[sensor_const]
        )

    def _get_entity_state_for_phase_sensor(
        self, phase: Phase, sensor_const: str
    ) -> float | None:
        """Get the state of the entity for a given phase and translation key."""
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
            msg = f"Invalid phase: {phase}"
            raise ValueError(msg)
        return entity_map
