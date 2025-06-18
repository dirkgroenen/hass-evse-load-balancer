"""Tests for the Keba charger implementation."""

from unittest.mock import MagicMock, patch, AsyncMock
import pytest
from homeassistant.helpers.device_registry import DeviceEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evse_load_balancer.meters.meter import Phase
from custom_components.evse_load_balancer.chargers.keba_charger import (
    KebaCharger,
    KebaEntityMap,
    KebaChargingStateMap,
    PhaseMode,
)
from custom_components.evse_load_balancer.const import CHARGER_DOMAIN_KEBA


@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    return hass


@pytest.fixture
def mock_config_entry():
    return MockConfigEntry(
        domain="evse_load_balancer",
        title="Keba Test Charger",
        data={"charger_type": "keba"},
        unique_id="test_keba_charger",
    )


@pytest.fixture
def mock_device_entry():
    device_entry = MagicMock(spec=DeviceEntry)
    device_entry.id = "keba_wallbox_abc123"
    device_entry.identifiers = {(CHARGER_DOMAIN_KEBA, "test_keba")}
    return device_entry


@pytest.fixture
def keba_charger(mock_hass, mock_config_entry, mock_device_entry):
    with patch(
        "custom_components.evse_load_balancer.chargers.keba_charger.KebaCharger.refresh_entities"
    ):
        charger = KebaCharger(
            hass=mock_hass,
            config_entry=mock_config_entry,
            device_entry=mock_device_entry,
        )
        charger._get_entity_state_by_unique_id = MagicMock()
        return charger


def test_is_charger_device_true(mock_device_entry):
    assert KebaCharger.is_charger_device(mock_device_entry)


def test_is_charger_device_false():
    device_entry = MagicMock(spec=DeviceEntry)
    device_entry.identifiers = {("other_domain", "something")}
    assert not KebaCharger.is_charger_device(device_entry)


@pytest.mark.asyncio
async def test_set_current_limit(keba_charger, mock_hass):
    test_limits = {Phase.L1: 16, Phase.L2: 14, Phase.L3: 15}
    await keba_charger.set_current_limit(test_limits)
    mock_hass.services.async_call.assert_called_once_with(
        domain=CHARGER_DOMAIN_KEBA,
        service="set_current",
        service_data={
            "device_id": "keba_wallbox_abc123",
            "current": 14,
        },
        blocking=True,
    )


def test_compose_unique_id(keba_charger):
    unique_id = keba_charger._compose_unique_id(KebaEntityMap.MaxCurrent)
    assert unique_id == "keba_wallbox_abc123_max_current"


def test_get_current_limit_success(keba_charger):
    keba_charger._get_entity_state_by_unique_id.return_value = "16"
    result = keba_charger.get_current_limit()
    assert result == {Phase.L1: 16, Phase.L2: 16, Phase.L3: 16}


def test_get_current_limit_missing_entity(keba_charger):
    keba_charger._get_entity_state_by_unique_id.return_value = None
    result = keba_charger.get_current_limit()
    assert result is None


def test_get_max_current_limit(keba_charger):
    result = keba_charger.get_max_current_limit()
    assert result == {Phase.L1: 32, Phase.L2: 32, Phase.L3: 32}


def test_car_connected_true(keba_charger):
    for status in [
        KebaChargingStateMap.ReadyToCharge,
        KebaChargingStateMap.Charging,
        KebaChargingStateMap.Interrupted,
    ]:
        keba_charger._get_entity_state_by_unique_id.return_value = status
        assert keba_charger.car_connected() is True


def test_car_connected_false(keba_charger):
    for status in [
        KebaChargingStateMap.Startup,
        KebaChargingStateMap.NotReady,
        KebaChargingStateMap.Error,
        None,
    ]:
        keba_charger._get_entity_state_by_unique_id.return_value = status
        assert keba_charger.car_connected() is False


def test_can_charge_true(keba_charger):
    for status in [
        KebaChargingStateMap.ReadyToCharge,
        KebaChargingStateMap.Charging,
    ]:
        keba_charger._get_entity_state_by_unique_id.return_value = status
        assert keba_charger.can_charge() is True


def test_can_charge_false(keba_charger):
    for status in [
        KebaChargingStateMap.Startup,
        KebaChargingStateMap.NotReady,
        KebaChargingStateMap.Error,
        KebaChargingStateMap.Interrupted,
        None,
    ]:
        keba_charger._get_entity_state_by_unique_id.return_value = status
        keba_charger._compose_unique_id = MagicMock(return_value="keba_wallbox_abc123_charging_state")
        assert keba_charger.can_charge() is False


def test_set_phase_mode_valid(keba_charger):
    try:
        keba_charger.set_phase_mode(PhaseMode.SINGLE, Phase.L1)
        assert True
    except ValueError:
        pytest.fail("set_phase_mode raised ValueError unexpectedly!")


def test_set_phase_mode_invalid(keba_charger):
    with pytest.raises(ValueError) as excinfo:
        keba_charger.set_phase_mode("invalid_mode", Phase.L1)
    assert "Invalid mode" in str(excinfo.value)
