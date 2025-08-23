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
        # cf.CONF_PHASE_SENSOR_PRODUCTION: "po1",
        cf.CONF_PHASE_SENSOR_CONSUMPTION: "p1",
        cf.CONF_PHASE_SENSOR_VOLTAGE: "u1",
    },
    cf.CONF_PHASE_KEY_TWO: {
        # cf.CONF_PHASE_SENSOR_PRODUCTION: "po2",
        cf.CONF_PHASE_SENSOR_CONSUMPTION: "p2",
        cf.CONF_PHASE_SENSOR_VOLTAGE: "u2",
    },
    cf.CONF_PHASE_KEY_THREE: {
        # cf.CONF_PHASE_SENSOR_PRODUCTION: "po3",
        cf.CONF_PHASE_SENSOR_CONSUMPTION: "p3",
        cf.CONF_PHASE_SENSOR_VOLTAGE: "u3",
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
        active_power_w = self.get_active_phase_power(phase)
        voltage_state = self._get_entity_state_for_phase_sensor(
            phase, cf.CONF_PHASE_SENSOR_VOLTAGE
        )

        if None in [active_power_w, voltage_state]:
            _LOGGER.warning(
                (
                    "Missing states for one of phase %s: active_power: %s, ",
                    "voltage: %s. Are the entities enabled?",
                ),
                phase,
                active_power_w,
                voltage_state,
            )
            return None
        # convert kW to W in order to calculate the current
        return floor(active_power_w * 1000.0 / voltage_state) if voltage_state else None

    def get_active_phase_power(self, phase: Phase) -> float | None:
        """Return the active power on a given phase."""
        consumption_state = self._get_entity_state_for_phase_sensor(
            phase, cf.CONF_PHASE_SENSOR_CONSUMPTION
        )
        #production_state = self._get_entity_state_for_phase_sensor(
        #    phase, cf.CONF_PHASE_SENSOR_PRODUCTION
        #)

        if consumption_state is None:
            _LOGGER.warning(
                "Missing state for one of phase %s: consumption: %s",
                phase,
                consumption_state,
            )
            return None
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
