"""Tests for the Lektrico charger implementation."""

from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from homeassistant.helpers.device_registry import DeviceEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evse_load_balancer.meters.meter import Phase
from custom_components.evse_load_balancer.chargers.lektrico_charger import (
    LektricoCharger,
    LektricoEntityMap,
    LektricoStatusMap,
    LEKTRICO_HW_MAX_CURRENT,
    LEKTRICO_HW_MIN_CURRENT,
)
from custom_components.evse_load_balancer.chargers.charger import PhaseMode
from custom_components.evse_load_balancer.const import CHARGER_DOMAIN_LEKTRICO


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
        title="Lektrico Test Charger",
        data={"charger_type": "lektrico"},
        unique_id="test_lektrico_charger",
    )


@pytest.fixture
def mock_device_entry():
    """Create a mock DeviceEntry object for testing."""
    device_entry = MagicMock(spec=DeviceEntry)
    device_entry.id = "test_device_id"
    device_entry.identifiers = {(CHARGER_DOMAIN_LEKTRICO, "test_charger")}
    return device_entry


@pytest.fixture
def lektrico_charger(mock_hass, mock_config_entry, mock_device_entry):
    """Create a LektricoCharger instance for testing."""
    with patch(
        "custom_components.evse_load_balancer.chargers.lektrico_charger.LektricoCharger.refresh_entities"
    ):
        charger = LektricoCharger(
            hass=mock_hass,
            config_entry=mock_config_entry,
            device_entry=mock_device_entry,
        )
        # Mock the _get_entity_state_by_key and _get_entity_id_by_key methods
        charger._get_entity_state_by_key = MagicMock()
        charger._get_entity_id_by_key = MagicMock()
        return charger


def test_is_charger_device_true(mock_device_entry):
    """Test is_charger_device returns True for Lektrico devices."""
    mock_device_entry.identifiers = {(CHARGER_DOMAIN_LEKTRICO, "test_charger")}
    assert LektricoCharger.is_charger_device(mock_device_entry) is True


def test_is_charger_device_false():
    """Test is_charger_device returns False for non-Lektrico devices."""
    mock_device_entry = MagicMock(spec=DeviceEntry)
    mock_device_entry.identifiers = {("other_domain", "test_charger")}
    assert LektricoCharger.is_charger_device(mock_device_entry) is False


async def test_set_phase_mode_single(lektrico_charger, mock_hass):
    """Test setting phase mode to single phase."""
    # Setup mock entity ID
    lektrico_charger._get_entity_id_by_key.return_value = "switch.test_force_single_phase"

    # Call the method
    await lektrico_charger.set_phase_mode(PhaseMode.SINGLE)

    # Verify service call was made with correct parameters
    mock_hass.services.async_call.assert_called_once_with(
        domain="switch",
        service="turn_on",
        service_data={"entity_id": "switch.test_force_single_phase"},
        blocking=True,
    )


async def test_set_phase_mode_multi(lektrico_charger, mock_hass):
    """Test setting phase mode to multi phase."""
    # Setup mock entity ID
    lektrico_charger._get_entity_id_by_key.return_value = "switch.test_force_single_phase"

    # Call the method
    await lektrico_charger.set_phase_mode(PhaseMode.MULTI)

    # Verify service call was made with correct parameters
    mock_hass.services.async_call.assert_called_once_with(
        domain="switch",
        service="turn_off",
        service_data={"entity_id": "switch.test_force_single_phase"},
        blocking=True,
    )


async def test_set_phase_mode_invalid(lektrico_charger):
    """Test setting an invalid phase mode raises ValueError."""
    with pytest.raises(ValueError) as excinfo:
        # Using a string instead of PhaseMode enum should raise ValueError
        await lektrico_charger.set_phase_mode("invalid_mode")
    assert "Invalid mode" in str(excinfo.value)


async def test_set_current_limit_normal_values(lektrico_charger, mock_hass):
    """Test setting current limits with normal values."""
    # Setup test data
    test_limits = {
        Phase.L1: 16,
        Phase.L2: 14,
        Phase.L3: 15,
    }
    lektrico_charger._get_entity_id_by_key.return_value = "number.test_dynamic_limit"

    # Call the method
    await lektrico_charger.set_current_limit(test_limits)

    # Verify service call was made with correct parameters
    mock_hass.services.async_call.assert_called_once_with(
        domain="number",
        service="set_value",
        service_data={
            "entity_id": "number.test_dynamic_limit",
            "value": 14,  # Should use minimum of the values
        },
        blocking=True,
    )


async def test_set_current_limit_clamping_max(lektrico_charger, mock_hass):
    """Test setting current limits above hardware maximum gets clamped."""
    # Setup test data with values above max
    test_limits = {
        Phase.L1: 40,
        Phase.L2: 50,
        Phase.L3: 45,
    }
    lektrico_charger._get_entity_id_by_key.return_value = "number.test_dynamic_limit"

    # Call the method
    await lektrico_charger.set_current_limit(test_limits)

    # Verify service call was made with clamped value
    mock_hass.services.async_call.assert_called_once_with(
        domain="number",
        service="set_value",
        service_data={
            "entity_id": "number.test_dynamic_limit",
            "value": LEKTRICO_HW_MAX_CURRENT,  # Should be clamped to max
        },
        blocking=True,
    )


async def test_set_current_limit_clamping_min(lektrico_charger, mock_hass):
    """Test setting current limits below hardware minimum gets clamped."""
    # Setup test data with values below min
    test_limits = {
        Phase.L1: -5,
        Phase.L2: -10,
        Phase.L3: -2,
    }
    lektrico_charger._get_entity_id_by_key.return_value = "number.test_dynamic_limit"

    # Call the method
    await lektrico_charger.set_current_limit(test_limits)

    # Verify service call was made with clamped value
    mock_hass.services.async_call.assert_called_once_with(
        domain="number",
        service="set_value",
        service_data={
            "entity_id": "number.test_dynamic_limit",
            "value": LEKTRICO_HW_MIN_CURRENT,  # Should be clamped to min
        },
        blocking=True,
    )


def test_get_current_limit_success(lektrico_charger):
    """Test retrieving the current limit when entity exists."""
    # Mock the entity state
    lektrico_charger._get_entity_state_by_key.return_value = 16

    # Call the method
    result = lektrico_charger.get_current_limit()

    # Verify results
    assert result == {Phase.L1: 16, Phase.L2: 16, Phase.L3: 16}
    lektrico_charger._get_entity_state_by_key.assert_called_once_with(
        LektricoEntityMap.DynamicChargerLimit
    )


def test_get_current_limit_string_value(lektrico_charger):
    """Test retrieving the current limit when entity returns string value."""
    # Mock the entity state as string
    lektrico_charger._get_entity_state_by_key.return_value = "20"

    # Call the method
    result = lektrico_charger.get_current_limit()

    # Verify results
    assert result == {Phase.L1: 20, Phase.L2: 20, Phase.L3: 20}


def test_get_max_current_limit_success(lektrico_charger):
    """Test retrieving the max current limit when entity exists."""
    # Mock the entity state
    lektrico_charger._get_entity_state_by_key.return_value = 32

    # Call the method
    result = lektrico_charger.get_max_current_limit()

    # Verify results
    assert result == {Phase.L1: 32, Phase.L2: 32, Phase.L3: 32}
    lektrico_charger._get_entity_state_by_key.assert_called_once_with(
        LektricoEntityMap.MaxChargerLimit
    )


def test_get_max_current_limit_string_value(lektrico_charger):
    """Test retrieving the max current limit when entity returns string value."""
    # Mock the entity state as string
    lektrico_charger._get_entity_state_by_key.return_value = "32"

    # Call the method
    result = lektrico_charger.get_max_current_limit()

    # Verify results
    assert result == {Phase.L1: 32, Phase.L2: 32, Phase.L3: 32}


def test_has_synced_phase_limits(lektrico_charger):
    """Test that Lektrico charger always has synced phase limits."""
    assert lektrico_charger.has_synced_phase_limits() is True


def test_car_connected_true(lektrico_charger):
    """Test car_connected returns True for valid statuses."""
    for status in [
        LektricoStatusMap.Connected,
        LektricoStatusMap.Charging,
        LektricoStatusMap.Paused,
        LektricoStatusMap.PausedByScheduler,
    ]:
        # Mock the status
        lektrico_charger._get_entity_state_by_key.return_value = status

        # Call the method
        result = lektrico_charger.car_connected()

        # Verify results
        assert result is True


def test_car_connected_false(lektrico_charger):
    """Test car_connected returns False for invalid statuses."""
    for status in [
        LektricoStatusMap.Available,
        LektricoStatusMap.Error,
        LektricoStatusMap.Locked,
        LektricoStatusMap.Authentication,
        LektricoStatusMap.Updating,
        None,  # Test with no status
    ]:
        # Mock the status
        lektrico_charger._get_entity_state_by_key.return_value = status

        # Call the method
        result = lektrico_charger.car_connected()

        # Verify results
        assert result is False


def test_can_charge_true(lektrico_charger):
    """Test can_charge returns True for valid statuses."""
    for status in [
        LektricoStatusMap.Connected,
        LektricoStatusMap.Charging,
    ]:
        # Mock the status
        lektrico_charger._get_entity_state_by_key.return_value = status

        # Call the method
        result = lektrico_charger.can_charge()

        # Verify results
        assert result is True


def test_can_charge_false(lektrico_charger):
    """Test can_charge returns False for invalid statuses."""
    for status in [
        LektricoStatusMap.Available,
        LektricoStatusMap.Error,
        LektricoStatusMap.Locked,
        LektricoStatusMap.Authentication,
        LektricoStatusMap.Paused,
        LektricoStatusMap.PausedByScheduler,
        LektricoStatusMap.Updating,
        None,  # Test with no status
    ]:
        # Mock the status
        lektrico_charger._get_entity_state_by_key.return_value = status

        # Call the method
        result = lektrico_charger.can_charge()

        # Verify results
        assert result is False


async def test_async_setup(lektrico_charger):
    """Test async_setup method (currently no-op)."""
    # Should not raise an exception
    await lektrico_charger.async_setup()


async def test_async_unload(lektrico_charger):
    """Test async_unload method (currently no-op)."""
    # Should not raise an exception
    await lektrico_charger.async_unload()


def test_get_status_private_method(lektrico_charger):
    """Test the private _get_status method."""
    # Mock the entity state
    test_status = LektricoStatusMap.Charging
    lektrico_charger._get_entity_state_by_key.return_value = test_status

    # Call the private method
    result = lektrico_charger._get_status()

    # Verify results
    assert result == test_status
    lektrico_charger._get_entity_state_by_key.assert_called_once_with(
        LektricoEntityMap.Status
    )


def test_get_status_none(lektrico_charger):
    """Test _get_status returns None when entity state is None."""
    # Mock the entity state to return None
    lektrico_charger._get_entity_state_by_key.return_value = None

    # Call the private method
    result = lektrico_charger._get_status()

    # Verify results
    assert result is None
