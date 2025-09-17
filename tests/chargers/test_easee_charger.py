"""Tests for the Easee charger implementation."""

from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from homeassistant.helpers.device_registry import DeviceEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evse_load_balancer.meters.meter import Phase
from custom_components.evse_load_balancer.chargers.easee_charger import (
    EaseeCharger,
    EaseeEntityMap,
    EaseeStatusMap,
    PhaseMode,
)
from custom_components.evse_load_balancer.const import CHARGER_DOMAIN_EASEE


@pytest.fixture
def mock_hass():
    """Create a mock HomeAssistant instance for testing."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a mock ConfigEntry for the tests."""
    return MockConfigEntry(
        domain="evse_load_balancer",
        title="Easee Test Charger",
        data={"charger_type": "easee"},
        unique_id="test_easee_charger",
    )


@pytest.fixture
def mock_device_entry():
    """Create a mock DeviceEntry object for testing."""
    device_entry = MagicMock(spec=DeviceEntry)
    device_entry.id = "test_device_id"
    device_entry.identifiers = {("easee", "test_charger")}
    return device_entry


@pytest.fixture
def easee_charger(mock_hass, mock_config_entry, mock_device_entry):
    """Create an EaseeCharger instance for testing."""
    with patch(
        "custom_components.evse_load_balancer.chargers.easee_charger.EaseeCharger.refresh_entities"
    ):
        charger = EaseeCharger(
            hass=mock_hass,
            config_entry=mock_config_entry,
            device_entry=mock_device_entry,
        )
        # Mock the _get_entity_state_by_translation_key method
        charger._get_entity_state_by_translation_key = MagicMock()
        return charger


async def test_set_current_limit(easee_charger, mock_hass):
    """Test setting current limits on the Easee charger."""
    # Setup test data
    test_limits = {
        Phase.L1: 16,
        Phase.L2: 14,
        Phase.L3: 15,
    }

    # Call the method
    await easee_charger.set_current_limit(test_limits)

    # Verify service call was made with correct parameters
    mock_hass.services.async_call.assert_called_once_with(
        domain=CHARGER_DOMAIN_EASEE,
        service="set_charger_dynamic_limit",
        service_data={
            "device_id": "test_device_id",
            "current": 14,  # Should use minimum of the values
            "time_to_live": 0,
        },
        blocking=True,
    )


def test_get_current_limit_success(easee_charger):
    """Test retrieving the current limit when entity exists."""
    # Mock the entity state
    easee_charger._get_entity_state_by_translation_key.return_value = "16"

    # Call the method
    result = easee_charger.get_current_limit()
    assert result == {Phase.L1: 16, Phase.L2: 16, Phase.L3: 16}
    easee_charger._get_entity_state_by_translation_key.assert_called_once_with(
        EaseeEntityMap.DynamicChargerLimit
    )


def test_get_current_limit_missing_entity(easee_charger):
    """Test retrieving the current limit when entity doesn't exist."""
    # Mock the entity state to return None (missing entity)
    easee_charger._get_entity_state_by_translation_key.return_value = None

    # Call the method
    result = easee_charger.get_current_limit()
    assert result is None
    easee_charger._get_entity_state_by_translation_key.assert_called_once_with(
        EaseeEntityMap.DynamicChargerLimit
    )


def test_get_max_current_limit_success(easee_charger):
    """Test retrieving the max current limit when entity exists."""
    # Mock the entity state
    easee_charger._get_entity_state_by_translation_key.return_value = "32"

    # Call the method
    result = easee_charger.get_max_current_limit()
    assert result == {Phase.L1: 32, Phase.L2: 32, Phase.L3: 32}
    easee_charger._get_entity_state_by_translation_key.assert_called_once_with(
        EaseeEntityMap.MaxChargerLimit
    )


def test_get_max_current_limit_missing_entity(easee_charger):
    """Test retrieving the max current limit when entity doesn't exist."""
    # Mock the entity state to return None (missing entity)
    easee_charger._get_entity_state_by_translation_key.return_value = None

    # Call the method
    result = easee_charger.get_max_current_limit()
    assert result is None
    easee_charger._get_entity_state_by_translation_key.assert_called_once_with(
        EaseeEntityMap.MaxChargerLimit
    )


def test_car_connected_true(easee_charger):
    """Test car_connected returns True for valid statuses."""
    for status in [
        EaseeStatusMap.AwaitingStart,
        EaseeStatusMap.Charging,
        EaseeStatusMap.Completed,
        EaseeStatusMap.ReadyToCharge,
    ]:
        easee_charger._get_entity_state_by_translation_key.return_value = status

        result = easee_charger.car_connected()

        assert result is True


def test_car_connected_false(easee_charger):
    """Test car_connected returns False for invalid statuses."""
    for status in [
        EaseeStatusMap.Disconnected,
        EaseeStatusMap.Error,
        EaseeStatusMap.AwaitingAuthorization,
        EaseeStatusMap.DeAuthorization,
        None,  # Test with no status
    ]:
        easee_charger._get_entity_state_by_translation_key.return_value = status

        result = easee_charger.car_connected()

        assert result is False


def test_can_charge_true(easee_charger):
    """Test can_charge returns True for valid statuses."""
    for status in [
        EaseeStatusMap.AwaitingStart,
        EaseeStatusMap.Charging,
        EaseeStatusMap.ReadyToCharge,
    ]:
        easee_charger._get_entity_state_by_translation_key.return_value = status

        result = easee_charger.can_charge()

        assert result is True


def test_can_charge_false(easee_charger):
    """Test can_charge returns False for invalid statuses."""
    for status in [
        EaseeStatusMap.Disconnected,
        EaseeStatusMap.Error,
        EaseeStatusMap.Completed,
        EaseeStatusMap.AwaitingAuthorization,
        EaseeStatusMap.DeAuthorization,
        None,  # Test with no status
    ]:
        easee_charger._get_entity_state_by_translation_key.return_value = status

        result = easee_charger.can_charge()

        assert result is False


def test_is_charging_true(easee_charger):
    """Test is_charging returns True for valid statuses."""
    easee_charger._get_entity_state_by_translation_key.return_value = EaseeStatusMap.Charging
    result = easee_charger.is_charging()

    assert result is True


def test_is_charging_false(easee_charger):
    """Test is_charging returns False for invalid statuses."""
    for status in [
        EaseeStatusMap.Disconnected,
        EaseeStatusMap.Error,
        EaseeStatusMap.Completed,
        EaseeStatusMap.AwaitingAuthorization,
        EaseeStatusMap.DeAuthorization,
        EaseeStatusMap.AwaitingStart,
        EaseeStatusMap.ReadyToCharge,
        None,
    ]:
        easee_charger._get_entity_state_by_translation_key.return_value = status

        result = easee_charger.is_charging()

        assert result is False


def test_set_phase_mode_valid(easee_charger):
    """Test setting a valid phase mode."""
    # This is currently a no-op in the implementation
    # but we should test that it doesn't raise an exception
    try:
        easee_charger.set_phase_mode(PhaseMode.SINGLE, Phase.L1)
        assert True  # No exception raised
    except ValueError:
        pytest.fail("set_phase_mode raised ValueError unexpectedly!")


def test_set_phase_mode_invalid(easee_charger):
    """Test setting an invalid phase mode raises ValueError."""
    with pytest.raises(ValueError) as excinfo:
        # Using a string instead of PhaseMode enum should raise ValueError
        easee_charger.set_phase_mode("invalid_mode", Phase.L1)
    assert "Invalid mode" in str(excinfo.value)
