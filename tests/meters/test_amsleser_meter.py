"""Tests for the AmsLeser Meter implementation."""

from unittest.mock import MagicMock
import pytest
from homeassistant.helpers.device_registry import DeviceEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evse_load_balancer.meters.amsleser_meter import AmsleserMeter
from custom_components.evse_load_balancer.meters.meter import Phase
from custom_components.evse_load_balancer import config_flow as cf


@pytest.fixture
def mock_hass():
    hass = MagicMock()
    return hass


@pytest.fixture
def mock_config_entry():
    return MockConfigEntry(
        domain="evse_load_balancer",
        title="AmsLeser Test Meter",
        data={"meter_type": "amsleser"},
        unique_id="test_amsleser_meter",
    )


@pytest.fixture
def mock_device_entry():
    device_entry = MagicMock(spec=DeviceEntry)
    device_entry.id = "amsleser_134"
    device_entry.identifiers = {("amsleser", "test_meter")}
    device_entry.manufacturer
    return device_entry


@pytest.fixture
def amsleser_meter(mock_hass, mock_config_entry, mock_device_entry):
    meter = AmsleserMeter(
        hass=mock_hass,
        config_entry=mock_config_entry,
        device_entry=mock_device_entry,
    )
    meter._get_entity_id_by_key = MagicMock()
    meter._get_entity_state = MagicMock()
    meter.entities = []
    return meter


def test_get_active_phase_power_consumption(amsleser_meter):
    amsleser_meter._get_entity_id_by_key.return_value = "sensor.p1"
    amsleser_meter._get_entity_state.return_value = 2300  # 2300W
    result = amsleser_meter.get_active_phase_power(Phase.L1)
    assert result == 2.3


#def test_get_active_phase_power_production(amsleser_meter):
#    amsleser_meter._get_entity_id_by_key.return_value = "sensor.p1"
#    amsleser_meter._get_entity_state.return_value = -1200  # -1200W
#    result = amsleser_meter.get_active_phase_power(Phase.L1)
#    assert result == -1.2


def test_get_active_phase_power_none(amsleser_meter):
    amsleser_meter._get_entity_id_by_key.return_value = "sensor.p1"
    amsleser_meter._get_entity_state.return_value = None
    result = amsleser_meter.get_active_phase_power(Phase.L1)
    assert result is None


def test_get_active_phase_current(amsleser_meter):
    amsleser_meter.get_active_phase_power = MagicMock(return_value=2.3)  # kW
    amsleser_meter._get_entity_state_for_phase_sensor = MagicMock(side_effect=lambda _, s: 230 if s == cf.CONF_PHASE_SENSOR_VOLTAGE else None)
    result = amsleser_meter.get_active_phase_current(Phase.L1)
    assert result == 10  # floor((2.3*1000)/230) = 10


def test_get_active_phase_current_missing_voltage(amsleser_meter):
    amsleser_meter.get_active_phase_power = MagicMock(return_value=2.3)
    amsleser_meter._get_entity_state_for_phase_sensor = MagicMock(return_value=None)
    result = amsleser_meter.get_active_phase_current(Phase.L1)
    assert result is None


def test_get_active_phase_current_missing_power(amsleser_meter):
    amsleser_meter.get_active_phase_power = MagicMock(return_value=None)
    amsleser_meter._get_entity_state_for_phase_sensor = MagicMock(side_effect=lambda _, s: 230 if s == cf.CONF_PHASE_SENSOR_VOLTAGE else None)
    result = amsleser_meter.get_active_phase_current(Phase.L1)
    assert result is None


def test_get_tracking_entities(amsleser_meter):
    class Entity:
        def __init__(self, entity_id, key):
            self.entity_id = entity_id
            self.unique_id = f"amsleser_{key}"
            self.key = key
    amsleser_meter.entities = [
        Entity("sensor.P1", "P1"),
        Entity("sensor.U1", "U1"),
        Entity("sensor.other", "other"),
    ]
    result = amsleser_meter.get_tracking_entities()
    assert "sensor.P1" in result
    assert "sensor.U1" in result
    assert "sensor.other" not in result


def test_get_entity_map_for_phase_valid(amsleser_meter):
    # Should not raise for valid phases
    for phase in [Phase.L1, Phase.L2, Phase.L3]:
        mapping = amsleser_meter._get_entity_map_for_phase(phase)
        assert isinstance(mapping, dict)


def test_get_entity_map_for_phase_invalid(amsleser_meter):
    with pytest.raises(ValueError):
        amsleser_meter._get_entity_map_for_phase("invalid_phase")
