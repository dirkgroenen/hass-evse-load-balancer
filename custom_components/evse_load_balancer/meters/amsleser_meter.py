"""AmsLeser implementation."""

import logging
from math import floor

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import (
    DeviceEntry,
)

from .. import config_flow as cf  # noqa: TID252
from ..ha_device import HaDevice  # noqa: TID252
from .meter import Meter, Phase

_LOGGER = logging.getLogger(__name__)

# Mapping entities from the AmsLeser MQTT device based on suffixes.
# Note that there is no support for production atm.
# @see https://wiki.amsleser.no/en/api/mqtt
ENTITY_REGISTRATION_MAP: dict[str, dict[str, str]] = {
    cf.CONF_PHASE_KEY_ONE: {
        # cf.CONF_PHASE_SENSOR_PRODUCTION: "PO1",
        cf.CONF_PHASE_SENSOR_CONSUMPTION: "P1",
        cf.CONF_PHASE_SENSOR_VOLTAGE: "U1",
        cf.CONF_PHASE_SENSOR_CURRENT: "I1",
    },
    cf.CONF_PHASE_KEY_TWO: {
        # cf.CONF_PHASE_SENSOR_PRODUCTION: "PO2",
        cf.CONF_PHASE_SENSOR_CONSUMPTION: "P2",
        cf.CONF_PHASE_SENSOR_VOLTAGE: "U2",
        cf.CONF_PHASE_SENSOR_CURRENT: "I2",
    },
    cf.CONF_PHASE_KEY_THREE: {
        # cf.CONF_PHASE_SENSOR_PRODUCTION: "PO3",
        cf.CONF_PHASE_SENSOR_CONSUMPTION: "P3",
        cf.CONF_PHASE_SENSOR_VOLTAGE: "U3",
        cf.CONF_PHASE_SENSOR_CURRENT: "I3",
    },
}


class AmsleserMeter(Meter, HaDevice):
    """AmsLeser implementation of the Meter class."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
    ) -> None:
        """Initialize the Meter instance."""
        Meter.__init__(self, hass, config_entry)
        HaDevice.__init__(self, hass, device_entry)
        self.refresh_entities()

    def get_active_phase_current(self, phase: Phase) -> int | None:
        """Return the active current on a given phase."""
        current_state = self._get_entity_state_for_phase_sensor(
            phase, cf.CONF_PHASE_SENSOR_CURRENT
        )

        if current_state is None:
            active_power_w = self.get_active_phase_power(phase)
            voltage_state = self._get_entity_state_for_phase_sensor(
                phase, cf.CONF_PHASE_SENSOR_VOLTAGE
            )

            if active_power_w is None or voltage_state is None:
                _LOGGER.warning(
                    (
                        "Missing states for one of phase %s: active_power: %s, ",
                        "voltage: %s, current: %s. Are the entities enabled?",
                    ),
                    phase,
                    active_power_w,
                    voltage_state,
                    current_state,
                )
                return None

            # convert kW to W in order to calculate the current
            current_state = floor(active_power_w * 1000.0 / voltage_state) if voltage_state else None
        
        return floor(current_state) if current_state else None

    def get_active_phase_power(self, phase: Phase) -> float | None:
        """Return the active power on a given phase."""
        consumption_state = self._get_entity_state_for_phase_sensor(
            phase, cf.CONF_PHASE_SENSOR_CONSUMPTION
        )

        if consumption_state is None:
            current_state = self._get_entity_state_for_phase_sensor(
                phase, cf.CONF_PHASE_SENSOR_CURRENT
            )
            voltage_state = self._get_entity_state_for_phase_sensor(
                phase, cf.CONF_PHASE_SENSOR_VOLTAGE
            )

            if current_state is None or voltage_state is None:
                _LOGGER.warning(
                    (
                        "Missing state for one of phase %s: consumption: %s, ",
                        "current: %s, voltage: %s."
                    ),
                    phase,
                    consumption_state,
                    current_state,
                    voltage_state,
                )
                return None

            consumption_state = current_state * voltage_state

        # Amsleser returns W, convert to kW for consistency.
        return consumption_state / 1000.0

    def get_tracking_entities(self) -> list[str]:
        """Return a list of entity IDs that should be tracked for this meter."""
        keys = [
            entity
            for phase in ENTITY_REGISTRATION_MAP.values()
            for entity in phase.values()
        ]
        return [
            e.entity_id
            for e in self.entities
            if any(e.unique_id.endswith(f"_{key}") for key in keys)
        ]

    def _get_entity_state_for_phase_sensor(
        self, phase: Phase, sensor_const: str
    ) -> float | None:
        """Get the state of the entity for a given phase and suffix."""
        entity_id = self._get_entity_id_by_key(
            self._get_entity_map_for_phase(phase)[sensor_const]
        )
        return self._get_entity_state(entity_id, float) if entity_id is not None else None

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
