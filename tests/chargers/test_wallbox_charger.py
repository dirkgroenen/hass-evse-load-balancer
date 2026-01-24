"""Tests for the Wallbox charger implementation."""

from unittest.mock import MagicMock, patch, AsyncMock

import pytest
from homeassistant.helpers.device_registry import DeviceEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evse_load_balancer.meters.meter import Phase
from custom_components.evse_load_balancer.chargers.wallbox_charger import (
    WallboxCharger,
    WallboxEntityMap,
    WallboxStatusMap,
    PhaseMode,
)


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
        title="Wallbox Test Charger",
        data={"charger_type": "wallbox"},
        unique_id="test_wallbox_charger",
    )


@pytest.fixture
def mock_device_entry():
    """Create a mock DeviceEntry object for testing."""
    device_entry = MagicMock(spec=DeviceEntry)
    device_entry.id = "test_device_id"
    device_entry.identifiers = {("wallbox", "test_charger")}
    return device_entry


@pytest.fixture
def wallbox_charger(mock_hass, mock_config_entry, mock_device_entry):
    """Create a WallboxCharger instance for testing."""
    with patch(
        "custom_components.evse_load_balancer.chargers.wallbox_charger.WallboxCharger.refresh_entities"
    ):
        charger = WallboxCharger(
            hass=mock_hass, config_entry=mock_config_entry, device_entry=mock_device_entry
        )
        # Mock entity lookup/state helpers
        charger._get_entity_state_by_translation_key = MagicMock()
        charger._get_entity_id_by_translation_key = MagicMock()
        return charger


async def test_set_current_limit(wallbox_charger, mock_hass):
    """Test setting current limits on the Wallbox charger."""
    test_limits = {Phase.L1: 16, Phase.L2: 14, Phase.L3: 15}
    entity_id = "number.wallbox_test_maximum_charging_current"

    wallbox_charger._get_entity_id_by_translation_key.return_value = entity_id

    await wallbox_charger.set_current_limit(test_limits)

    mock_hass.services.async_call.assert_called_once_with(
        domain="number",
        service="set_value",
        service_data={"entity_id": entity_id, "value": 14},
        blocking=True,
    )


def test_get_current_limit_success(wallbox_charger):
    """Test retrieving the current limit when entity exists."""
    wallbox_charger._get_entity_state_by_translation_key.return_value = "16"

    result = wallbox_charger.get_current_limit()
    assert result == {Phase.L1: 16, Phase.L2: 16, Phase.L3: 16}
    wallbox_charger._get_entity_state_by_translation_key.assert_called_with(
        WallboxEntityMap.DynamicChargerLimit
    )


def test_get_current_limit_missing_entity(wallbox_charger):
    """Test retrieving the current limit when entity doesn't exist."""
    wallbox_charger._get_entity_state_by_translation_key.return_value = None

    result = wallbox_charger.get_current_limit()
    assert result is None
    wallbox_charger._get_entity_state_by_translation_key.assert_called_with(
        WallboxEntityMap.DynamicChargerLimit
    )


def test_get_max_current_limit_success(wallbox_charger):
    """Test retrieving the max current limit when entity exists."""
    wallbox_charger._get_entity_state_by_translation_key.return_value = "32"

    result = wallbox_charger.get_max_current_limit()
    assert result == {Phase.L1: 32, Phase.L2: 32, Phase.L3: 32}
    wallbox_charger._get_entity_state_by_translation_key.assert_called_with(
        WallboxEntityMap.MaxChargerLimit
    )


def test_get_max_current_limit_missing_entity(wallbox_charger):
    """Test retrieving the max current limit when entity doesn't exist."""
    wallbox_charger._get_entity_state_by_translation_key.return_value = None

    result = wallbox_charger.get_max_current_limit()
    assert result is None
    wallbox_charger._get_entity_state_by_translation_key.assert_called_with(
        WallboxEntityMap.MaxChargerLimit
    )


def test_car_connected_and_can_charge_and_is_charging(wallbox_charger):
    """Test status mapping for connected/can_charge/is_charging."""
    # READY means no car connected
    wallbox_charger._get_entity_state_by_translation_key.return_value = WallboxStatusMap.Ready
    assert wallbox_charger.car_connected() is False
    assert wallbox_charger.can_charge() is False
    assert wallbox_charger.is_charging() is False

    # Waiting for car demand means car present but not charging
    wallbox_charger._get_entity_state_by_translation_key.return_value = WallboxStatusMap.WaitingForCarDemand
    assert wallbox_charger.car_connected() is True
    assert wallbox_charger.can_charge() is True
    assert wallbox_charger.is_charging() is False

    # Charging
    wallbox_charger._get_entity_state_by_translation_key.return_value = WallboxStatusMap.Charging
    assert wallbox_charger.car_connected() is True
    assert wallbox_charger.can_charge() is True
    assert wallbox_charger.is_charging() is True

    # Locked, car connected
    wallbox_charger._get_entity_state_by_translation_key.return_value = WallboxStatusMap.LockedCarConnected
    assert wallbox_charger.car_connected() is True


def test_is_charging_false_for_other_states(wallbox_charger):
    """is_charging returns False for non-charging states."""
    for status in [
        WallboxStatusMap.Disconnected,
        WallboxStatusMap.Error,
        WallboxStatusMap.Scheduled,
        WallboxStatusMap.WaitingInQueuePowerSharing,
        WallboxStatusMap.Unknown,
        None,
    ]:
        wallbox_charger._get_entity_state_by_translation_key.return_value = status
        assert wallbox_charger.is_charging() is False


def test_set_phase_mode_valid_and_invalid(wallbox_charger):
    """set_phase_mode accepts valid PhaseMode and rejects invalid values."""
    # Valid (no-op)
    try:
        wallbox_charger.set_phase_mode(PhaseMode.SINGLE, Phase.L1)
    except ValueError:
        pytest.fail("set_phase_mode raised ValueError unexpectedly!")

    # Invalid
    with pytest.raises(ValueError):
        wallbox_charger.set_phase_mode("invalid_mode", Phase.L1)
