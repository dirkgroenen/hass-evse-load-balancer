"""Tests for the Peblar charger implementation."""

from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest
from homeassistant.helpers.device_registry import DeviceEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evse_load_balancer.chargers.charger import PhaseMode
from custom_components.evse_load_balancer.chargers.peblar_charger import (
    PeblarCharger,
    PeblarEntityMap,
    PeblarStateMap,
)
from custom_components.evse_load_balancer.const import CHARGER_DOMAIN_PEBLAR, Phase


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
        title="Peblar Test Charger",
        data={"charger_type": "peblar"},
        unique_id="test_peblar_charger",
    )


@pytest.fixture
def mock_device_entry():
    """Create a mock DeviceEntry object for testing."""
    device_entry = MagicMock(spec=DeviceEntry)
    device_entry.id = "test_device_id"
    device_entry.identifiers = {(CHARGER_DOMAIN_PEBLAR, "test_charger")}
    return device_entry


@pytest.fixture
def peblar_charger(mock_hass, mock_config_entry, mock_device_entry):
    """Create a PeblarCharger instance for testing."""
    with patch(
        "custom_components.evse_load_balancer.chargers.peblar_charger.PeblarCharger.refresh_entities"
    ):
        charger = PeblarCharger(
            hass=mock_hass,
            config_entry=mock_config_entry,
            device_entry=mock_device_entry,
        )
        charger._get_entity_state_by_key = MagicMock()
        charger._get_entity_state_attrs_by_key = MagicMock()
        charger._get_entity_id_by_key = MagicMock()
        return charger


def test_is_charger_device_true(mock_device_entry):
    """Test is_charger_device returns True for Peblar devices."""
    assert PeblarCharger.is_charger_device(mock_device_entry) is True


def test_is_charger_device_false():
    """Test is_charger_device returns False for non-Peblar devices."""
    device_entry = MagicMock(spec=DeviceEntry)
    device_entry.identifiers = {("other_domain", "test_charger")}
    assert PeblarCharger.is_charger_device(device_entry) is False


def test_entity_map_keys_match_peblar_integration():
    """Test entity keys are aligned with Home Assistant Peblar integration."""
    assert PeblarEntityMap.State == "cp_state"
    assert PeblarEntityMap.ChargeLimit == "charge_current_limit"


async def test_set_phase_mode_single(peblar_charger, mock_hass):
    """Test setting phase mode to single phase."""
    peblar_charger._get_entity_id_by_key.return_value = "switch.test_force_single_phase"

    await peblar_charger.set_phase_mode(PhaseMode.SINGLE)

    mock_hass.services.async_call.assert_called_once_with(
        domain="switch",
        service="turn_on",
        service_data={"entity_id": "switch.test_force_single_phase"},
        blocking=True,
    )


async def test_set_phase_mode_multi(peblar_charger, mock_hass):
    """Test setting phase mode to multi phase."""
    peblar_charger._get_entity_id_by_key.return_value = "switch.test_force_single_phase"

    await peblar_charger.set_phase_mode(PhaseMode.MULTI)

    mock_hass.services.async_call.assert_called_once_with(
        domain="switch",
        service="turn_off",
        service_data={"entity_id": "switch.test_force_single_phase"},
        blocking=True,
    )


async def test_set_phase_mode_missing_switch_is_noop(peblar_charger, mock_hass):
    """Test missing force_single_phase switch does not raise and does not call service."""
    peblar_charger._get_entity_id_by_key.side_effect = ValueError("Missing switch")

    await peblar_charger.set_phase_mode(PhaseMode.SINGLE)

    mock_hass.services.async_call.assert_not_called()


async def test_set_phase_mode_invalid_raises(peblar_charger):
    """Test invalid phase mode raises ValueError."""
    with pytest.raises(ValueError) as exc_info:
        await peblar_charger.set_phase_mode("invalid_mode")
    assert "Invalid mode" in str(exc_info.value)


async def test_set_current_limit_below_min_turns_off_charge_switch(
    peblar_charger, mock_hass
):
    """Test current below min disables charging via charge switch."""
    peblar_charger._get_entity_id_by_key.side_effect = (
        lambda key: {
            PeblarEntityMap.ChargeLimit: "number.test_charge_current_limit",
            PeblarEntityMap.Charge: "switch.test_charge",
        }[key]
    )
    peblar_charger._get_entity_state_attrs_by_key.return_value = {"min": 6, "max": 20}

    await peblar_charger.set_current_limit({Phase.L1: 3, Phase.L2: 5, Phase.L3: 4})

    mock_hass.services.async_call.assert_called_once_with(
        domain="switch",
        service="turn_off",
        service_data={"entity_id": "switch.test_charge"},
        blocking=True,
    )


async def test_set_current_limit_sets_value_and_enables_charge_switch(
    peblar_charger, mock_hass
):
    """Test current at/above min updates limit and enables charging when needed."""
    peblar_charger._get_entity_id_by_key.side_effect = (
        lambda key: {
            PeblarEntityMap.ChargeLimit: "number.test_charge_current_limit",
            PeblarEntityMap.Charge: "switch.test_charge",
        }[key]
    )
    peblar_charger._get_entity_state_attrs_by_key.return_value = {"min": 6, "max": 20}
    peblar_charger._get_entity_state_by_key.return_value = "off"

    await peblar_charger.set_current_limit({Phase.L1: 8, Phase.L2: 10, Phase.L3: 9})

    mock_hass.services.async_call.assert_has_calls(
        [
            call(
                domain="number",
                service="set_value",
                service_data={"entity_id": "number.test_charge_current_limit", "value": 8},
                blocking=True,
            ),
            call(
                domain="switch",
                service="turn_on",
                service_data={"entity_id": "switch.test_charge"},
                blocking=True,
            ),
        ]
    )


async def test_set_current_limit_clamps_to_entity_max(peblar_charger, mock_hass):
    """Test current limit is clamped to max attribute for normal charging."""
    peblar_charger._get_entity_id_by_key.side_effect = (
        lambda key: {
            PeblarEntityMap.ChargeLimit: "number.test_charge_current_limit",
            PeblarEntityMap.Charge: "switch.test_charge",
        }[key]
    )
    peblar_charger._get_entity_state_attrs_by_key.return_value = {"min": 6, "max": 20}
    peblar_charger._get_entity_state_by_key.return_value = "on"

    await peblar_charger.set_current_limit({Phase.L1: 22, Phase.L2: 21, Phase.L3: 23})

    mock_hass.services.async_call.assert_called_once_with(
        domain="number",
        service="set_value",
        service_data={"entity_id": "number.test_charge_current_limit", "value": 20},
        blocking=True,
    )


async def test_set_current_limit_missing_entity_is_noop(peblar_charger, mock_hass):
    """Test missing charge current limit entity does not raise."""
    peblar_charger._get_entity_id_by_key.side_effect = ValueError("Missing number")

    await peblar_charger.set_current_limit({Phase.L1: 6, Phase.L2: 6, Phase.L3: 6})

    mock_hass.services.async_call.assert_not_called()


async def test_set_current_limit_empty_input_is_noop(peblar_charger, mock_hass):
    """Test empty current limit input does not call services."""
    await peblar_charger.set_current_limit({})
    mock_hass.services.async_call.assert_not_called()


def test_get_current_limit(peblar_charger):
    """Test getting the current limit."""
    peblar_charger._get_entity_state_by_key.side_effect = (
        lambda key: {
            PeblarEntityMap.Charge: "on",
            PeblarEntityMap.ChargeLimit: "16",
        }[key]
    )
    result = peblar_charger.get_current_limit()
    assert result == {Phase.L1: 16, Phase.L2: 16, Phase.L3: 16}


def test_get_current_limit_returns_zero_when_charge_switch_off(peblar_charger):
    """Test charge switch OFF is represented as 0A current limit."""
    peblar_charger._get_entity_state_by_key.side_effect = (
        lambda key: {
            PeblarEntityMap.Charge: "off",
            PeblarEntityMap.ChargeLimit: "16",
        }[key]
    )
    result = peblar_charger.get_current_limit()
    assert result == {Phase.L1: 0, Phase.L2: 0, Phase.L3: 0}


def test_get_current_limit_missing_charge_switch_returns_none(peblar_charger):
    """Test missing charge switch state returns unknown current limit."""

    def _mock_state(key):
        if key == PeblarEntityMap.Charge:
            raise ValueError("Missing switch")
        if key == PeblarEntityMap.ChargeLimit:
            return "16"
        return None

    peblar_charger._get_entity_state_by_key.side_effect = _mock_state
    result = peblar_charger.get_current_limit()
    assert result is None


def test_get_current_limit_invalid_returns_none(peblar_charger):
    """Test invalid current limit values return None."""
    peblar_charger._get_entity_state_by_key.side_effect = (
        lambda key: {
            PeblarEntityMap.Charge: "on",
            PeblarEntityMap.ChargeLimit: "invalid",
        }[key]
    )
    result = peblar_charger.get_current_limit()
    assert result is None


async def test_set_current_limit_unknown_charge_switch_state_does_not_toggle_switch(
    peblar_charger, mock_hass
):
    """Test unknown charge switch state updates limit without turn_on side-effects."""
    peblar_charger._get_entity_id_by_key.side_effect = (
        lambda key: {
            PeblarEntityMap.ChargeLimit: "number.test_charge_current_limit",
            PeblarEntityMap.Charge: "switch.test_charge",
        }[key]
    )
    peblar_charger._get_entity_state_attrs_by_key.return_value = {"min": 6, "max": 20}

    def _mock_state(key):
        if key == PeblarEntityMap.Charge:
            return None
        if key == PeblarEntityMap.ChargeLimit:
            return "16"
        return None

    peblar_charger._get_entity_state_by_key.side_effect = _mock_state

    await peblar_charger.set_current_limit({Phase.L1: 8, Phase.L2: 8, Phase.L3: 8})

    mock_hass.services.async_call.assert_called_once_with(
        domain="number",
        service="set_value",
        service_data={"entity_id": "number.test_charge_current_limit", "value": 8},
        blocking=True,
    )


def test_get_current_limit_missing_entity_returns_none(peblar_charger):
    """Test missing current limit entity returns None."""
    def _mock_state(key):
        if key == PeblarEntityMap.Charge:
            return "on"
        if key == PeblarEntityMap.ChargeLimit:
            raise ValueError("Missing number")
        return None

    peblar_charger._get_entity_state_by_key.side_effect = _mock_state
    result = peblar_charger.get_current_limit()
    assert result is None


def test_get_max_current_limit(peblar_charger):
    """Test getting maximum current limit from entity attributes."""
    peblar_charger._get_entity_state_attrs_by_key.return_value = {"max": 32}
    result = peblar_charger.get_max_current_limit()
    assert result == {Phase.L1: 32, Phase.L2: 32, Phase.L3: 32}


def test_get_max_current_limit_missing_returns_none(peblar_charger):
    """Test missing max attribute returns None."""
    peblar_charger._get_entity_state_attrs_by_key.return_value = {}
    result = peblar_charger.get_max_current_limit()
    assert result is None


def test_get_max_current_limit_missing_entity_returns_none(peblar_charger):
    """Test missing current limit entity returns None."""
    peblar_charger._get_entity_state_attrs_by_key.side_effect = ValueError(
        "Missing number"
    )
    result = peblar_charger.get_max_current_limit()
    assert result is None


def test_car_connected(peblar_charger):
    """Test car_connected logic."""
    peblar_charger._get_entity_state_by_key.return_value = PeblarStateMap.Charging
    assert peblar_charger.car_connected() is True

    peblar_charger._get_entity_state_by_key.return_value = PeblarStateMap.Suspended
    assert peblar_charger.car_connected() is True

    peblar_charger._get_entity_state_by_key.return_value = PeblarStateMap.NoEvConnected
    assert peblar_charger.car_connected() is False


def test_car_connected_missing_state_entity_returns_false(peblar_charger):
    """Test missing cp_state entity returns False."""
    peblar_charger._get_entity_state_by_key.side_effect = ValueError("Missing sensor")
    assert peblar_charger.car_connected() is False


def test_is_charging(peblar_charger):
    """Test is_charging logic."""
    peblar_charger._get_entity_state_by_key.return_value = PeblarStateMap.Charging
    assert peblar_charger.is_charging() is True

    peblar_charger._get_entity_state_by_key.return_value = PeblarStateMap.Suspended
    assert peblar_charger.is_charging() is False


def test_can_charge_true_when_connected_enabled_not_faulted(peblar_charger):
    """Test can_charge for connected, enabled, healthy state."""
    peblar_charger._get_entity_state_by_key.side_effect = (
        lambda key: {
            PeblarEntityMap.State: PeblarStateMap.Charging,
            PeblarEntityMap.Charge: "on",
        }[key]
    )
    assert peblar_charger.can_charge() is True


def test_can_charge_false_when_not_connected(peblar_charger):
    """Test can_charge for no EV connected."""
    peblar_charger._get_entity_state_by_key.side_effect = (
        lambda key: {
            PeblarEntityMap.State: PeblarStateMap.NoEvConnected,
            PeblarEntityMap.Charge: "on",
        }[key]
    )
    assert peblar_charger.can_charge() is False


def test_can_charge_true_when_charge_switch_off(peblar_charger):
    """Test can_charge when charge switch is off but EV is connected."""
    peblar_charger._get_entity_state_by_key.side_effect = (
        lambda key: {
            PeblarEntityMap.State: PeblarStateMap.Charging,
            PeblarEntityMap.Charge: "off",
        }[key]
    )
    assert peblar_charger.can_charge() is True


def test_can_charge_false_on_faulted_states(peblar_charger):
    """Test can_charge in fault/error/invalid states."""
    for state in (PeblarStateMap.Error, PeblarStateMap.Fault, PeblarStateMap.Invalid):
        peblar_charger._get_entity_state_by_key.side_effect = (
            lambda key, test_state=state: {
                PeblarEntityMap.State: test_state,
                PeblarEntityMap.Charge: "on",
            }[key]
        )
        assert peblar_charger.can_charge() is False
