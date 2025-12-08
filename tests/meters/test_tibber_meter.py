"""Tests for the Tibber Meter implementation."""

from unittest.mock import MagicMock
import pytest
from homeassistant.helpers.device_registry import DeviceEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evse_load_balancer.meters.tibber_meter import TibberMeter
from custom_components.evse_load_balancer.meters.meter import Phase


@pytest.fixture
def mock_hass():
    hass = MagicMock()
    return hass


@pytest.fixture
def mock_config_entry():
    return MockConfigEntry(
        domain="evse_load_balancer",
        title="Tibber Test Meter",
        data={"meter_type": "tibber"},
        unique_id="test_tibber_meter",
    )


@pytest.fixture
def mock_device_entry():
    device_entry = MagicMock(spec=DeviceEntry)
    device_entry.id = "tibber_12345"
    device_entry.identifiers = {("tibber", "test_meter")}
    return device_entry


@pytest.fixture
def tibber_meter(mock_hass, mock_config_entry, mock_device_entry):
    meter = TibberMeter(
        hass=mock_hass,
        config_entry=mock_config_entry,
        device_entry=mock_device_entry,
    )
    meter._get_entity_id_by_key = MagicMock()
    meter._get_entity_state = MagicMock()
    meter.entities = []
    return meter


def test_get_active_phase_current(tibber_meter):
    tibber_meter._get_entity_state_for_phase_sensor = MagicMock(return_value=10.5)
    result = tibber_meter.get_active_phase_current(Phase.L1)
    assert result == 10


def test_get_active_phase_current_none(tibber_meter):
    tibber_meter._get_entity_state_for_phase_sensor = MagicMock(return_value=None)
    result = tibber_meter.get_active_phase_current(Phase.L1)
    assert result is None


def test_get_tracking_entities(tibber_meter):
    class Entity:
        def __init__(self, entity_id, key):
            self.entity_id = entity_id
            self.unique_id = f"tibber_{key}"
            self.key = key

    tibber_meter.entities = [
        Entity("sensor.current_l1", "_rt_currentL1"),
        Entity("sensor.voltage_phase1", "_rt_voltagePhase1"),
        Entity("sensor.current_l2", "_rt_currentL2"),
        Entity("sensor.voltage_phase2", "_rt_voltagePhase2"),
        Entity("sensor.other", "_rt_other"),
    ]
    result = tibber_meter.get_tracking_entities()
    assert "sensor.current_l1" in result
    assert "sensor.voltage_phase1" in result
    assert "sensor.current_l2" in result
    assert "sensor.voltage_phase2" in result
    assert "sensor.other" not in result


def test_get_entity_map_for_phase_valid(tibber_meter):
    # Should not raise for valid phases
    for phase in [Phase.L1, Phase.L2, Phase.L3]:
        mapping = tibber_meter._get_entity_map_for_phase(phase)
        assert isinstance(mapping, dict)
        assert "current" in mapping
        assert "voltage" in mapping


def test_get_entity_map_for_phase_invalid(tibber_meter):
    with pytest.raises(ValueError):
        tibber_meter._get_entity_map_for_phase("invalid_phase")


def test_tibber_entity_map_keys():
    # Test that the entity map contains the correct Tibber sensor keys
    from custom_components.evse_load_balancer.meters.tibber_meter import (
        TIBBER_ENTITY_MAP,
    )
    import custom_components.evse_load_balancer.config_flow as cf

    assert cf.CONF_PHASE_KEY_ONE in TIBBER_ENTITY_MAP
    assert cf.CONF_PHASE_KEY_TWO in TIBBER_ENTITY_MAP
    assert cf.CONF_PHASE_KEY_THREE in TIBBER_ENTITY_MAP

    # Check that the correct Tibber sensor keys are used (current and voltage only)
    l1_map = TIBBER_ENTITY_MAP[cf.CONF_PHASE_KEY_ONE]
    assert l1_map["current"] == "currentL1"
    assert l1_map["voltage"] == "voltagePhase1"
    assert "power" not in l1_map  # Tibber Pulse doesn't provide per-phase power

    l2_map = TIBBER_ENTITY_MAP[cf.CONF_PHASE_KEY_TWO]
    assert l2_map["current"] == "currentL2"
    assert l2_map["voltage"] == "voltagePhase2"
    assert "power" not in l2_map

    l3_map = TIBBER_ENTITY_MAP[cf.CONF_PHASE_KEY_THREE]
    assert l3_map["current"] == "currentL3"
    assert l3_map["voltage"] == "voltagePhase3"
    assert "power" not in l3_map
