"""Tests for the Wallbox charger implementation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.device_registry import DeviceEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evse_load_balancer.chargers.charger import PhaseMode
from custom_components.evse_load_balancer.chargers.wallbox_charger import (
    WallboxCharger,
    WallboxEntityMap,
    WallboxStatusMap,
)
from custom_components.evse_load_balancer.const import CHARGER_DOMAIN_WALLBOX, Phase


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
        data={},
        unique_id="test_wallbox_charger",
    )


@pytest.fixture
def mock_device_entry():
    """Create a mock DeviceEntry object for testing."""
    device_entry = MagicMock(spec=DeviceEntry)
    device_entry.id = "wallbox_123"
    device_entry.identifiers = {(CHARGER_DOMAIN_WALLBOX, "test_charger")}
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
        charger._get_entity_state_by_translation_key = MagicMock()
        charger._get_entity_id_by_translation_key = MagicMock()
        return charger


def test_is_charger_device_true(mock_device_entry):
    """Test is_charger_device returns True for Wallbox devices."""
    assert WallboxCharger.is_charger_device(mock_device_entry) is True


def test_is_charger_device_false():
    """Test is_charger_device returns False for non-Wallbox devices."""
    device = MagicMock(spec=DeviceEntry)
    device.identifiers = {("other_domain", "test_charger")}
    assert WallboxCharger.is_charger_device(device) is False


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


def test_get_current_limit_float_value(wallbox_charger):
    """Test retrieving the current limit when entity returns float string."""
    wallbox_charger._get_entity_state_by_translation_key.return_value = "16.5"

    result = wallbox_charger.get_current_limit()
    assert result == {Phase.L1: 16, Phase.L2: 16, Phase.L3: 16}


def test_get_current_limit_missing(wallbox_charger):
    """Test retrieving the current limit when entity doesn't exist."""
    wallbox_charger._get_entity_state_by_translation_key.return_value = None

    result = wallbox_charger.get_current_limit()
    assert result is None


def test_get_max_current_limit_success(wallbox_charger):
    """Test retrieving the max current limit when entity exists."""
    wallbox_charger._get_entity_state_by_translation_key.return_value = "32"

    result = wallbox_charger.get_max_current_limit()
    assert result == {Phase.L1: 32, Phase.L2: 32, Phase.L3: 32}
    wallbox_charger._get_entity_state_by_translation_key.assert_called_with(
        WallboxEntityMap.MaxChargerLimit
    )


def test_get_max_current_limit_float_value(wallbox_charger):
    """Test retrieving the max current limit when entity returns float string."""
    wallbox_charger._get_entity_state_by_translation_key.return_value = "32.0"

    result = wallbox_charger.get_max_current_limit()
    assert result == {Phase.L1: 32, Phase.L2: 32, Phase.L3: 32}


def test_get_max_current_limit_missing(wallbox_charger):
    """Test retrieving the max current limit when entity doesn't exist."""
    wallbox_charger._get_entity_state_by_translation_key.return_value = None

    result = wallbox_charger.get_max_current_limit()
    assert result is None


def test_has_synced_phase_limits(wallbox_charger):
    """Test that Wallbox charger always has synced phase limits."""
    assert wallbox_charger.has_synced_phase_limits() is True


def test_car_connected_true(wallbox_charger):
    """Test car_connected returns True for connected statuses."""
    for status in [
        WallboxStatusMap.Charging,
        WallboxStatusMap.Discharging,
        WallboxStatusMap.Paused,
        WallboxStatusMap.Scheduled,
        WallboxStatusMap.WaitingForCarDemand,
        WallboxStatusMap.Waiting,
        WallboxStatusMap.LockedCarConnected,
        WallboxStatusMap.WaitingInQueuePowerSharing,
        WallboxStatusMap.WaitingInQueuePowerBoost,
        WallboxStatusMap.WaitingInQueueEcoSmart,
        WallboxStatusMap.WaitingMidFailed,
        WallboxStatusMap.WaitingMidSafety,
    ]:
        wallbox_charger._get_entity_state_by_translation_key.return_value = status
        assert wallbox_charger.car_connected() is True, f"Expected car_connected=True for {status}"


def test_car_connected_false(wallbox_charger):
    """Test car_connected returns False for disconnected statuses."""
    for status in [
        WallboxStatusMap.Ready,
        WallboxStatusMap.Disconnected,
        WallboxStatusMap.Error,
        WallboxStatusMap.Locked,
        WallboxStatusMap.Updating,
        WallboxStatusMap.Unknown,
        None,
    ]:
        wallbox_charger._get_entity_state_by_translation_key.return_value = status
        assert wallbox_charger.car_connected() is False, f"Expected car_connected=False for {status}"


def test_can_charge_true(wallbox_charger):
    """Test can_charge returns True for chargeable statuses."""
    for status in [
        WallboxStatusMap.Charging,
        WallboxStatusMap.Discharging,
        WallboxStatusMap.WaitingForCarDemand,
        WallboxStatusMap.Paused,
    ]:
        wallbox_charger._get_entity_state_by_translation_key.return_value = status
        assert wallbox_charger.can_charge() is True, f"Expected can_charge=True for {status}"


def test_can_charge_false(wallbox_charger):
    """Test can_charge returns False for non-chargeable statuses."""
    for status in [
        WallboxStatusMap.Ready,
        WallboxStatusMap.Disconnected,
        WallboxStatusMap.Error,
        WallboxStatusMap.Locked,
        WallboxStatusMap.LockedCarConnected,
        WallboxStatusMap.Scheduled,
        WallboxStatusMap.Waiting,
        WallboxStatusMap.Updating,
        WallboxStatusMap.WaitingInQueuePowerSharing,
        WallboxStatusMap.WaitingInQueuePowerBoost,
        WallboxStatusMap.WaitingInQueueEcoSmart,
        WallboxStatusMap.WaitingMidFailed,
        WallboxStatusMap.WaitingMidSafety,
        WallboxStatusMap.Unknown,
        None,
    ]:
        wallbox_charger._get_entity_state_by_translation_key.return_value = status
        assert wallbox_charger.can_charge() is False, f"Expected can_charge=False for {status}"


def test_is_charging_true(wallbox_charger):
    """Test is_charging returns True when actively charging."""
    wallbox_charger._get_entity_state_by_translation_key.return_value = WallboxStatusMap.Charging
    assert wallbox_charger.is_charging() is True


def test_is_charging_false(wallbox_charger):
    """Test is_charging returns False for non-charging statuses."""
    for status in [
        WallboxStatusMap.Discharging,
        WallboxStatusMap.Paused,
        WallboxStatusMap.Scheduled,
        WallboxStatusMap.WaitingForCarDemand,
        WallboxStatusMap.Waiting,
        WallboxStatusMap.Disconnected,
        WallboxStatusMap.Error,
        WallboxStatusMap.Ready,
        WallboxStatusMap.Locked,
        WallboxStatusMap.LockedCarConnected,
        WallboxStatusMap.Updating,
        WallboxStatusMap.WaitingInQueuePowerSharing,
        WallboxStatusMap.WaitingInQueuePowerBoost,
        WallboxStatusMap.WaitingMidFailed,
        WallboxStatusMap.WaitingMidSafety,
        WallboxStatusMap.WaitingInQueueEcoSmart,
        WallboxStatusMap.Unknown,
        None,
    ]:
        wallbox_charger._get_entity_state_by_translation_key.return_value = status
        assert wallbox_charger.is_charging() is False, f"Expected is_charging=False for {status}"


def test_set_phase_mode_valid(wallbox_charger):
    """Test set_phase_mode accepts valid PhaseMode values."""
    wallbox_charger.set_phase_mode(PhaseMode.SINGLE, Phase.L1)
    wallbox_charger.set_phase_mode(PhaseMode.MULTI, Phase.L1)


def test_set_phase_mode_invalid(wallbox_charger):
    """Test set_phase_mode rejects invalid values."""
    with pytest.raises(ValueError, match="Invalid mode"):
        wallbox_charger.set_phase_mode("invalid_mode", Phase.L1)


async def test_async_setup(wallbox_charger):
    """Test async_setup method (no-op)."""
    await wallbox_charger.async_setup()


async def test_async_unload(wallbox_charger):
    """Test async_unload method (no-op)."""
    await wallbox_charger.async_unload()
