"""Tests for the Zaptec charger implementation."""

from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from homeassistant.helpers.device_registry import DeviceEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evse_load_balancer.meters.meter import Phase
from custom_components.evse_load_balancer.chargers.zaptec_charger import (
    ZaptecCharger,
    ZaptecEntityMap,
    ZaptecStatusMap,
    PhaseMode,
)
from custom_components.evse_load_balancer.const import CHARGER_DOMAIN_ZAPTEC


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
        title="Zaptec Test Charger",
        data={"charger_type": "zaptec"},
        unique_id="test_zaptec_charger",
    )


@pytest.fixture
def mock_device_entry():
    """Create a mock DeviceEntry object for testing."""
    device_entry = MagicMock(spec=DeviceEntry)
    device_entry.id = "test_device_id"
    device_entry.identifiers = {(CHARGER_DOMAIN_ZAPTEC, "test_charger")}
    return device_entry


@pytest.fixture
def zaptec_charger(mock_hass, mock_config_entry, mock_device_entry):
    """Create a ZaptecCharger instance for testing."""
    with patch(
        "custom_components.evse_load_balancer.chargers.zaptec_charger.ZaptecCharger.refresh_entities"
    ):
        charger = ZaptecCharger(
            hass=mock_hass,
            config_entry=mock_config_entry,
            device_entry=mock_device_entry,
        )
        # Mock the methods used to get entity information
        charger._get_entity_state_by_translation_key = MagicMock()
        charger._get_entity_id_by_translation_key = MagicMock(return_value="number.zaptec_charger_max_current")
        return charger


async def test_set_current_limit(zaptec_charger, mock_hass):
    """Test setting current limits on the Zaptec charger."""
    # Setup test data
    test_limits = {
        Phase.L1: 16,
        Phase.L2: 14,
        Phase.L3: 15,
    }

    # Call the method
    await zaptec_charger.set_current_limit(test_limits)

    # Verify service call was made with correct parameters
    mock_hass.services.async_call.assert_called_once_with(
        domain="number",
        service="set_value",
        service_data={
            "entity_id": "number.zaptec_charger_max_current",
            "value": 14,  # Should use minimum of the values
        },
        blocking=True,
    )


def test_get_current_limit_success(zaptec_charger):
    """Test retrieving the current limit when entity exists."""
    # Mock the entity state
    zaptec_charger._get_entity_state_by_translation_key.return_value = "16.0"

    # Call the method
    result = zaptec_charger.get_current_limit()

    # Verify results
    assert result == {Phase.L1: 16, Phase.L2: 16, Phase.L3: 16}
    zaptec_charger._get_entity_state_by_translation_key.assert_called_once_with(
        ZaptecEntityMap.MaxChargingCurrent
    )


def test_get_current_limit_none_state(zaptec_charger):
    """Test retrieving the current limit when entity state is None."""
    # Mock the entity state to return None
    zaptec_charger._get_entity_state_by_translation_key.return_value = None

    # Call the method
    result = zaptec_charger.get_current_limit()

    # Verify results
    assert result is None
    zaptec_charger._get_entity_state_by_translation_key.assert_called_once_with(
        ZaptecEntityMap.MaxChargingCurrent
    )


def test_get_current_limit_invalid_state(zaptec_charger):
    """Test retrieving the current limit when entity state is invalid."""
    # Mock the entity state to return an invalid value
    zaptec_charger._get_entity_state_by_translation_key.return_value = "not-a-number"

    # Call the method
    result = zaptec_charger.get_current_limit()

    # Verify results
    assert result is None
    zaptec_charger._get_entity_state_by_translation_key.assert_called_once_with(
        ZaptecEntityMap.MaxChargingCurrent
    )


def test_get_max_current_limit_success(zaptec_charger):
    """Test retrieving the max current limit when entity exists."""
    # Mock the entity state
    zaptec_charger._get_entity_state_by_translation_key.return_value = "32"

    # Call the method
    result = zaptec_charger.get_max_current_limit()

    # Verify results
    assert result == {Phase.L1: 32, Phase.L2: 32, Phase.L3: 32}
    zaptec_charger._get_entity_state_by_translation_key.assert_called_once_with(
        ZaptecEntityMap.AvailableCurrent
    )


def test_get_max_current_limit_none_state(zaptec_charger):
    """Test retrieving the max current limit when entity state is None."""
    # Mock the entity state to return None
    zaptec_charger._get_entity_state_by_translation_key.return_value = None

    # Call the method
    result = zaptec_charger.get_max_current_limit()

    # Verify results
    assert result is None
    zaptec_charger._get_entity_state_by_translation_key.assert_called_once_with(
        ZaptecEntityMap.AvailableCurrent
    )


def test_get_max_current_limit_float_value(zaptec_charger):
    """Test retrieving the max current limit when entity returns a float."""
    # Mock the entity state to return a float value
    zaptec_charger._get_entity_state_by_translation_key.return_value = "32.5"

    # Call the method
    result = zaptec_charger.get_max_current_limit()

    # Verify results
    assert result == {Phase.L1: 32, Phase.L2: 32, Phase.L3: 32}
    zaptec_charger._get_entity_state_by_translation_key.assert_called_once_with(
        ZaptecEntityMap.AvailableCurrent
    )


def test_car_connected_true(zaptec_charger):
    """Test car_connected returns True for valid statuses."""
    for status in [
        ZaptecStatusMap.ConnectedRequesting,
        ZaptecStatusMap.ConnectedCharging,
        ZaptecStatusMap.ConnectedFinished,
    ]:
        # Reset the mock
        zaptec_charger._get_entity_state_by_translation_key.reset_mock()

        # Mock the status
        zaptec_charger._get_entity_state_by_translation_key.return_value = status

        # Call the method
        result = zaptec_charger.car_connected()

        # Verify results
        assert result is True
        zaptec_charger._get_entity_state_by_translation_key.assert_called_once_with(
            ZaptecEntityMap.Status
        )


def test_car_connected_false(zaptec_charger):
    """Test car_connected returns False for invalid statuses."""
    for status in [
        ZaptecStatusMap.Disconnected,
        ZaptecStatusMap.Unknown,
        None,  # Test with no status
    ]:
        # Reset the mock
        zaptec_charger._get_entity_state_by_translation_key.reset_mock()

        # Mock the status
        zaptec_charger._get_entity_state_by_translation_key.return_value = status

        # Call the method
        result = zaptec_charger.car_connected()

        # Verify results
        assert result is False
        zaptec_charger._get_entity_state_by_translation_key.assert_called_once_with(
            ZaptecEntityMap.Status
        )


def test_can_charge_true(zaptec_charger):
    """Test can_charge returns True for valid statuses when car is connected."""
    for status in [
        ZaptecStatusMap.ConnectedCharging,
        ZaptecStatusMap.ConnectedRequesting,
    ]:
        # Reset the mock
        zaptec_charger._get_entity_state_by_translation_key.reset_mock()

        # Mock the status
        zaptec_charger._get_entity_state_by_translation_key.return_value = status

        # Call the method
        result = zaptec_charger.can_charge()

        # Verify results
        assert result is True
        zaptec_charger._get_entity_state_by_translation_key.assert_called_with(
            ZaptecEntityMap.Status
        )


def test_can_charge_false(zaptec_charger):
    """Test can_charge returns False for invalid statuses or when car is not connected."""
    # First test: invalid status even with car connected
    zaptec_charger._get_entity_state_by_translation_key.reset_mock()

    # Create a side effect for car_connected check and status check
    def get_entity_side_effect(key):
        if key == ZaptecEntityMap.Status:
            return ZaptecStatusMap.Unknown
        return None

    zaptec_charger._get_entity_state_by_translation_key.side_effect = get_entity_side_effect

    # Call the method
    result = zaptec_charger.can_charge()

    # Verify results
    assert result is False

    # Second test: car not connected (disconnected status)
    zaptec_charger._get_entity_state_by_translation_key.reset_mock()
    zaptec_charger._get_entity_state_by_translation_key.return_value = ZaptecStatusMap.Disconnected

    # Call the method
    result = zaptec_charger.can_charge()

    # Verify results
    assert result is False


def test_is_charging_true(zaptec_charger):
    """Test is_charging returns True for valid statuses when car is connected."""
    zaptec_charger._get_entity_state_by_translation_key.reset_mock()

    zaptec_charger._get_entity_state_by_translation_key.return_value = ZaptecStatusMap.ConnectedCharging

    result = zaptec_charger.is_charging()

    assert result is True


def test_is_charging_false(zaptec_charger):
    """Test is_charging returns False for invalid statuses or when car is not connected."""
    zaptec_charger._get_entity_state_by_translation_key.reset_mock()

    zaptec_charger._get_entity_state_by_translation_key.return_value = ZaptecStatusMap.ConnectedRequesting

    result = zaptec_charger.is_charging()

    assert result is False


def test_set_phase_mode_valid(zaptec_charger):
    """Test setting a valid phase mode."""
    # This is currently a no-op in the implementation
    # but we should test that it doesn't raise an exception
    try:
        zaptec_charger.set_phase_mode(PhaseMode.SINGLE, Phase.L1)
        assert True  # No exception raised
    except ValueError:
        pytest.fail("set_phase_mode raised ValueError unexpectedly!")


def test_set_phase_mode_invalid(zaptec_charger):
    """Test setting an invalid phase mode raises ValueError."""
    with pytest.raises(ValueError) as excinfo:
        # Using a string instead of PhaseMode enum should raise ValueError
        zaptec_charger.set_phase_mode("invalid_mode", Phase.L1)
    assert "Invalid mode" in str(excinfo.value)
