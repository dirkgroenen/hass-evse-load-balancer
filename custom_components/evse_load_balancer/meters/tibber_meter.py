"""Tibber Meter implementation."""

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import (
    DeviceEntry,
)

from .. import config_flow as cf  # noqa: TID252
from ..ha_device import HaDevice  # noqa: TID252
from .meter import Meter, Phase

_LOGGER = logging.getLogger(__name__)

# Mapping entities from the Tibber component based on their key
# @https://github.com/home-assistant/core/blob/dev/homeassistant/components/tibber/sensor.py
TIBBER_ENTITY_MAP: dict[str, dict[str, str]] = {
    cf.CONF_PHASE_KEY_ONE: {
        cf.CONF_PHASE_SENSOR_CURRENT: "currentL1",
        cf.CONF_PHASE_SENSOR_VOLTAGE: "voltagePhase1",
        cf.CONF_PHASE_SENSOR: "power",  # Tibber only has total power, not per phase
    },
    cf.CONF_PHASE_KEY_TWO: {
        cf.CONF_PHASE_SENSOR_CURRENT: "currentL2",
        cf.CONF_PHASE_SENSOR_VOLTAGE: "voltagePhase2",
        cf.CONF_PHASE_SENSOR: "power",  # Tibber only has total power, not per phase
    },
    cf.CONF_PHASE_KEY_THREE: {
        cf.CONF_PHASE_SENSOR_CURRENT: "currentL3",
        cf.CONF_PHASE_SENSOR_VOLTAGE: "voltagePhase3",
        cf.CONF_PHASE_SENSOR: "power",  # Tibber only has total power, not per phase
    },
}


class TibberMeter(Meter, HaDevice):
    """Tibber Meter implementation of the Meter class."""

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
            _LOGGER.warning(
                "Missing state for phase %s: current. Is the entity enabled?",
                phase,
            )
            return None
        # Tibber returns current in Amperes, return as integer
        return int(current_state) if current_state is not None else None

    def get_active_phase_power(self, phase: Phase) -> float | None:
        """
        Return the active power on a given phase (kW).

        Note: Tibber only provides total power, not per-phase power.
        TODO: Verify how to distinguish (per-phase) production/consumption
        """
        current_state = self._get_entity_state_for_phase_sensor(
            phase, cf.CONF_PHASE_SENSOR_CURRENT
        )
        voltage_state = self._get_entity_state_for_phase_sensor(
            phase, cf.CONF_PHASE_SENSOR_VOLTAGE
        )
        power_state = self._get_entity_state_for_phase_sensor(
            phase, cf.CONF_PHASE_SENSOR
        )
        if None in [current_state, voltage_state, power_state]:
            _LOGGER.warning(
                "Missing state for power, voltage or current. Are the entities enabled?"
            )
            return None

        phase_power_w = voltage_state * current_state
        return phase_power_w / 1000.0  # Convert to kW

    def get_tracking_entities(self) -> list[str]:
        """Return a list of entity IDs that should be tracked for this meter."""
        keys = [
            entity for phase in TIBBER_ENTITY_MAP.values() for entity in phase.values()
        ]
        # Remove duplicates (since "power" appears for all phases)
        unique_keys = list(set(keys))

        return [
            e.entity_id
            for e in self.entities
            if any(e.unique_id.endswith(f"_rt_{key}") for key in unique_keys)
        ]

    def _get_entity_id_for_phase_sensor(
        self, phase: Phase, sensor_const: str
    ) -> str | None:
        """Get the entity_id for a given phase and key."""
        return self._get_entity_id_by_key(
            self._get_entity_map_for_phase(phase)[sensor_const]
        )

    def _get_entity_state_for_phase_sensor(
        self, phase: Phase, sensor_const: str
    ) -> float | None:
        """Get the state of the entity for a given phase and key."""
        entity_id = self._get_entity_id_for_phase_sensor(phase, sensor_const)
        return self._get_entity_state(entity_id, float)

    def _get_entity_map_for_phase(self, phase: Phase) -> dict:
        if phase == Phase.L1:
            return TIBBER_ENTITY_MAP[cf.CONF_PHASE_KEY_ONE]
        if phase == Phase.L2:
            return TIBBER_ENTITY_MAP[cf.CONF_PHASE_KEY_TWO]
        if phase == Phase.L3:
            return TIBBER_ENTITY_MAP[cf.CONF_PHASE_KEY_THREE]
        msg = f"Invalid phase: {phase}"
        raise ValueError(msg)
