"""VERATTI V4 three-phase meter using Tuya Local's direct current readings."""

from math import ceil

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import ATTR_UNIT_OF_MEASUREMENT, UnitOfElectricCurrent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from ..const import VERATTI_MANUFACTURER, VERATTI_MODEL, Phase  # noqa: TID252
from ..tuya_local_device import (  # noqa: TID252
    TuyaLocalDevice,
    finite_number,
    is_tuya_local_device,
)
from .meter import Meter

CURRENT_IDS = {
    Phase.L1: "sensor_current_a",
    Phase.L2: "sensor_current_b",
    Phase.L3: "sensor_current_c",
}


class VerattiMeter(Meter, TuyaLocalDevice):
    """Measure whole-house current on each phase without a power-factor assumption."""

    def __init__(
        self, hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry
    ) -> None:
        """Resolve all three enabled current sensors."""
        Meter.__init__(self, hass, config_entry)
        TuyaLocalDevice.__init__(self, hass, device_entry)
        for config_id in CURRENT_IDS.values():
            self.entity_id(config_id)

    @staticmethod
    def is_meter_device(device: DeviceEntry) -> bool:
        """Match the known Tuya Local profile only."""
        return is_tuya_local_device(device, VERATTI_MANUFACTURER, VERATTI_MODEL)

    def get_active_phase_current(self, phase: Phase) -> int | None:
        """Round current up so integer allocation does not overstate spare capacity."""
        try:
            entity_id = self.entity_id(CURRENT_IDS[phase])
        except ValueError:
            # A required sensor can be disabled or removed after setup.
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        # This meter reports phase measurements on changes. Tuya Local marks
        # its sensors unavailable when the device connection is lost; an
        # unchanged cached reading remains usable while the device is online.
        value = finite_number(state.state)
        if value is None or value < 0:
            return None
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        if unit == UnitOfElectricCurrent.MILLIAMPERE:
            value /= 1000
        elif unit != UnitOfElectricCurrent.AMPERE:
            return None
        return ceil(value)

    def get_tracking_entities(self) -> list[str]:
        """Return sensor IDs, including renamed entities."""
        return [self.entity_id(config_id) for config_id in CURRENT_IDS.values()]
