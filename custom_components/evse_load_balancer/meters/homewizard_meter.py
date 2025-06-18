"""DSMR Meter implementation."""

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

# Mapping entities from the HomeWizard component based on their translation key
# @https://github.com/home-assistant/core/blob/dev/homeassistant/components/homewizard/sensor.py
HOMEWIZARD_ENTITY_MAP: dict[str, dict[str, str]] = {
    cf.CONF_PHASE_KEY_ONE: {
        cf.CONF_PHASE_SENSOR: "active_power_l1",
        cf.CONF_PHASE_SENSOR_VOLTAGE: "voltage_l1",
    },
    cf.CONF_PHASE_KEY_TWO: {
        cf.CONF_PHASE_SENSOR: "active_power_l2",
        cf.CONF_PHASE_SENSOR_VOLTAGE: "voltage_l2",
    },
    cf.CONF_PHASE_KEY_THREE: {
        cf.CONF_PHASE_SENSOR: "active_power_l3",
        cf.CONF_PHASE_SENSOR_VOLTAGE: "voltage_l3",
    },
}


class HomeWizardMeter(Meter, HaDevice):
    """HomeWizard P1 Meter implementation of the Meter class."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
    ) -> None:
        """Initialize the Meter instance."""
        Meter.__init__(self, hass, config_entry)
        HaDevice.__init__(self, hass, device_entry)
        self.refresh_entities()

    def get_active_phase_current(self, phase: Phase) -> int | None:
        """Return the active current on a given phase."""
        active_power = self.get_active_phase_power(phase)
        voltage_state = self._get_entity_state_for_phase_sensor(
            phase, cf.CONF_PHASE_SENSOR_VOLTAGE
        )
        if None in [active_power, voltage_state]:
            _LOGGER.warning(
                (
                    "Missing states for one of phase %s: active_power: %s, ",
                    "voltage: %s. Are the entities enabled?",
                ),
                phase,
                active_power,
                voltage_state,
            )
            return None
        # convert kW to W in order to calculate the current
        return floor((active_power * 1000) / voltage_state) if voltage_state else None

    def get_active_phase_power(self, phase: Phase) -> float | None:
        """
        Return the active power on a given phase (kW).

        Positive=consumption, negative=production.
        """
        power_state = self._get_entity_state_for_phase_sensor(
            phase, cf.CONF_PHASE_SENSOR
        )
        if power_state is None:
            _LOGGER.warning(
                "Missing state for phase %s: active_power. Is the entity enabled?",
                phase,
            )
            return None
        # HomeWizard returns W, convert to kW for consistency
        return power_state / 1000.0

    def get_tracking_entities(self) -> list[str]:
        """Return a list of entity IDs that should be tracked for this meter."""
        translation_keys = [
            entity
            for phase in HOMEWIZARD_ENTITY_MAP.values()
            for entity in phase.values()
        ]
        return [
            e.entity_id for e in self.entities if e.translation_key in translation_keys
        ]

    def _get_entity_id_for_phase_sensor(
        self, phase: Phase, sensor_const: str
    ) -> float | None:
        """Get the entity_id for a given phase and translation key."""
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
        if phase == Phase.L1:
            return HOMEWIZARD_ENTITY_MAP[cf.CONF_PHASE_KEY_ONE]
        if phase == Phase.L2:
            return HOMEWIZARD_ENTITY_MAP[cf.CONF_PHASE_KEY_TWO]
        if phase == Phase.L3:
            return HOMEWIZARD_ENTITY_MAP[cf.CONF_PHASE_KEY_THREE]
        msg = f"Invalid phase: {phase}"
        raise ValueError(msg)
