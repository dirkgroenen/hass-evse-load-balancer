"""Tests for the HomeWizard Meter implementation."""

from unittest.mock import MagicMock
import pytest
from homeassistant.helpers.device_registry import DeviceEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evse_load_balancer.meters.homewizard_meter import HomeWizardMeter
from custom_components.evse_load_balancer.meters.meter import Phase


@pytest.fixture
def mock_hass():
    hass = MagicMock()
    return hass


@pytest.fixture
def mock_config_entry():
    return MockConfigEntry(
        domain="evse_load_balancer",
        title="HomeWizard Test Meter",
        data={"meter_type": "homewizard"},
        unique_id="test_homewizard_meter",
    )


@pytest.fixture
def mock_device_entry():
    device_entry = MagicMock(spec=DeviceEntry)
    device_entry.id = "homewizard_134"
    device_entry.identifiers = {("homewizard", "test_meter")}
    return device_entry


@pytest.fixture
def homewizard_meter(mock_hass, mock_config_entry, mock_device_entry):
    meter = HomeWizardMeter(
        hass=mock_hass,
        config_entry=mock_config_entry,
        device_entry=mock_device_entry,
    )
    meter._get_entity_id_by_key = MagicMock()
    meter._get_entity_state = MagicMock()
    meter.entities = []
    return meter


def test_get_active_phase_power_consumption(homewizard_meter):
    homewizard_meter._get_entity_id_by_key.return_value = "sensor.active_power_l1_w"
    homewizard_meter._get_entity_state.return_value = 2300  # 2300W
    result = homewizard_meter.get_active_phase_power(Phase.L1)
    assert result == 2.3


def test_get_active_phase_power_production(homewizard_meter):
    homewizard_meter._get_entity_id_by_key.return_value = "sensor.active_power_l1_w"
    homewizard_meter._get_entity_state.return_value = -1200  # -1200W
    result = homewizard_meter.get_active_phase_power(Phase.L1)
    assert result == -1.2


def test_get_active_phase_power_none(homewizard_meter):
    homewizard_meter._get_entity_id_by_key.return_value = "sensor.active_power_l1_w"
    homewizard_meter._get_entity_state.return_value = None
    result = homewizard_meter.get_active_phase_power(Phase.L1)
    assert result is None


def test_get_active_phase_current(homewizard_meter):
    homewizard_meter.get_active_phase_power = MagicMock(return_value=2.3)  # kW
    homewizard_meter._get_entity_state_for_phase_sensor = MagicMock(return_value=230)  # V
    result = homewizard_meter.get_active_phase_current(Phase.L1)
    assert result == 10  # floor((2.3*1000)/230) = 10


def test_get_active_phase_current_missing_voltage(homewizard_meter):
    homewizard_meter.get_active_phase_power = MagicMock(return_value=2.3)
    homewizard_meter._get_entity_state_for_phase_sensor = MagicMock(return_value=None)
    result = homewizard_meter.get_active_phase_current(Phase.L1)
    assert result is None


def test_get_active_phase_current_missing_power(homewizard_meter):
    homewizard_meter.get_active_phase_power = MagicMock(return_value=None)
    homewizard_meter._get_entity_state_for_phase_sensor = MagicMock(return_value=230)
    result = homewizard_meter.get_active_phase_current(Phase.L1)
    assert result is None


def test_get_tracking_entities(homewizard_meter):
    class Entity:
        def __init__(self, entity_id, key):
            self.entity_id = entity_id
            self.unique_id = f"homewizard_{key}"
            self.key = key
    homewizard_meter.entities = [
        Entity("sensor.active_power_l1_w", "active_power_l1_w"),
        Entity("sensor.active_voltage_l1_v", "active_voltage_l1_v"),
        Entity("sensor.other", "other"),
    ]
    result = homewizard_meter.get_tracking_entities()
    assert "sensor.active_power_l1_w" in result
    assert "sensor.active_voltage_l1_v" in result
    assert "sensor.other" not in result


def test_get_entity_map_for_phase_valid(homewizard_meter):
    # Should not raise for valid phases
    for phase in [Phase.L1, Phase.L2, Phase.L3]:
        mapping = homewizard_meter._get_entity_map_for_phase(phase)
        assert isinstance(mapping, dict)


def test_get_entity_map_for_phase_invalid(homewizard_meter):
    with pytest.raises(ValueError):
        homewizard_meter._get_entity_map_for_phase("invalid_phase")
