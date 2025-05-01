import unittest
from unittest.mock import MagicMock, patch
from homeassistant.helpers.entity import EntityDescription
from custom_components.evse_load_balancer.coordinator import EVSELoadBalancerCoordinator
from custom_components.evse_load_balancer.coordinator_entity import CoordinatorEntity
from custom_components.evse_load_balancer.const import DOMAIN
import pytest
from unittest.mock import patch
from pytest_homeassistant_custom_component.common import MockConfigEntry


@pytest.fixture
def mock_coordinator(hass):
    """Create a mock coordinator fixture."""
    coordinator = MagicMock(spec=EVSELoadBalancerCoordinator)
    coordinator.config_entry = MockConfigEntry(domain=DOMAIN, entry_id="test_entry_id")
    coordinator.hass = hass
    return coordinator


@pytest.fixture
def entity_description():
    """Create an entity description fixture."""
    return EntityDescription(key="test_property")


@pytest.fixture
def coordinator_entity(hass, mock_coordinator, entity_description):
    """Create a coordinator entity fixture."""
    with patch("homeassistant.helpers.entity.Entity.__init__", return_value=None):
        entity = CoordinatorEntity(mock_coordinator, entity_description)
    return entity


async def test_coordinator_entity_attributes(coordinator_entity, mock_coordinator, entity_description):
    """Test the entity attributes using pytest fixtures."""
    # Test basic attributes
    assert coordinator_entity.entity_description == entity_description
    assert coordinator_entity._coordinator == mock_coordinator
    assert coordinator_entity._attr_name == "Test Property"
    assert coordinator_entity._attr_unique_id == "test_entry_id_test_property"
    assert coordinator_entity._attr_should_poll is False


async def test_device_info(coordinator_entity):
    """Test device info attributes with pytest."""
    device_info = coordinator_entity._attr_device_info
    assert device_info["identifiers"] == {(DOMAIN, "test_entry_id")}
    assert device_info["name"] == "EVSE Load Balancer"
    assert device_info["manufacturer"] == "EnergyLabs"
    assert "configuration_url" in device_info


async def test_entity_registration(coordinator_entity, mock_coordinator):
    """Test entity registration with pytest."""
    mock_coordinator.register_entity.assert_called_once_with(coordinator_entity)

    # Test unregistration
    await coordinator_entity.async_will_remove_from_hass()
    mock_coordinator.unregister_entity.assert_called_once_with(coordinator_entity)


@pytest.mark.parametrize(
    "attr_value,expected",
    [
        (42, 42),  # Test with integer
        ("test", "test"),  # Test with string
        (None, None),  # Test with None
        (True, True),  # Test with boolean
    ]
)
async def test_get_value_parametrized(mock_coordinator, entity_description, attr_value, expected):
    """Test _get_value_in_coordinator with different value types."""
    with patch("homeassistant.helpers.entity.Entity.__init__", return_value=None):
        entity = CoordinatorEntity(mock_coordinator, entity_description)

    setattr(mock_coordinator, "test_property", attr_value)
    result = entity._get_value_in_coordinator()
    assert result == expected


async def test_entity_state_update(hass, mock_coordinator, entity_description):
    """Test that entity writes state when value changes."""
    with patch("homeassistant.helpers.entity.Entity.__init__", return_value=None):
        entity = CoordinatorEntity(mock_coordinator, entity_description)

    with patch.object(entity, "async_write_ha_state") as mock_write_state:
        entity._set_value_in_coordinator(100)
        mock_write_state.assert_called_once()
        assert getattr(mock_coordinator, "test_property") == 100


async def test_multiple_entities_with_coordinator(mock_coordinator):
    """Test multiple entities interacting with the same coordinator."""
    desc1 = EntityDescription(key="property1")
    desc2 = EntityDescription(key="property2")

    with patch("homeassistant.helpers.entity.Entity.__init__", return_value=None):
        entity1 = CoordinatorEntity(mock_coordinator, desc1)
        entity1.async_write_ha_state = MagicMock()
        entity2 = CoordinatorEntity(mock_coordinator, desc2)
        entity2.async_write_ha_state = MagicMock()

    # Set values for both entities
    entity1._set_value_in_coordinator("value1")
    entity2._set_value_in_coordinator("value2")

    # Check that the values are correctly stored in the coordinator
    assert getattr(mock_coordinator, "property1") == "value1"
    assert getattr(mock_coordinator, "property2") == "value2"

    # Check cross-entity access
    assert entity1._get_value_in_coordinator() == "value1"
    assert entity2._get_value_in_coordinator() == "value2"


async def test_entity_unique_ids(mock_coordinator):
    """Test that entities get unique IDs based on their keys."""
    desc1 = EntityDescription(key="sensor1")
    desc2 = EntityDescription(key="sensor2")

    with patch("homeassistant.helpers.entity.Entity.__init__", return_value=None):
        entity1 = CoordinatorEntity(mock_coordinator, desc1)
        entity2 = CoordinatorEntity(mock_coordinator, desc2)

    assert entity1._attr_unique_id == "test_entry_id_sensor1"
    assert entity2._attr_unique_id == "test_entry_id_sensor2"
    assert entity1._attr_unique_id != entity2._attr_unique_id
