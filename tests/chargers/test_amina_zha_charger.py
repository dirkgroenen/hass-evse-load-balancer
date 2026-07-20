"""Tests for the ZHA-connected Amina S charger implementation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.helpers.device_registry import DeviceEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evse_load_balancer.chargers.amina_charger import (
    AMINA_HW_MAX_CURRENT,
)
from custom_components.evse_load_balancer.chargers.amina_zha_charger import (
    AMINA_ZHA_ONOFF_UNIQUE_ID_SUFFIX,
    AminaZhaCharger,
    AminaZhaEntityMap,
)
from custom_components.evse_load_balancer.chargers.charger import PhaseMode
from custom_components.evse_load_balancer.const import (
    CHARGER_DOMAIN_ZHA,
    CHARGER_MANUFACTURER_AMINA,
    CHARGER_MANUFACTURER_AMINA_ZHA,
    Phase,
)

ONOFF_ENTITY_ID = "switch.amina_s"


def _make_device_entry(
    domain=CHARGER_DOMAIN_ZHA,
    identifier="00:0d:6f:00:11:22:33:44",
    manufacturer=CHARGER_MANUFACTURER_AMINA_ZHA,
) -> MagicMock:
    device_entry = MagicMock(spec=DeviceEntry)
    device_entry.id = "test_device_id"
    device_entry.identifiers = {(domain, identifier)}
    device_entry.manufacturer = manufacturer
    return device_entry


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
        title="Amina ZHA Test Charger",
        data={"charger_type": "amina_zha"},
        unique_id="test_amina_zha_charger",
    )


@pytest.fixture
def mock_device_entry():
    """Create a mock DeviceEntry object for testing."""
    return _make_device_entry()


@pytest.fixture
def amina_zha_charger(mock_hass, mock_config_entry, mock_device_entry):
    """Create an AminaZhaCharger instance with lookups mocked out."""
    with patch(
        "custom_components.evse_load_balancer.chargers.amina_zha_charger.AminaZhaCharger.refresh_entities"
    ):
        charger = AminaZhaCharger(
            hass=mock_hass,
            config_entry=mock_config_entry,
            device_entry=mock_device_entry,
        )
        charger.entities = []
        charger._get_entity_id_by_translation_key = MagicMock()
        charger._get_entity_state_by_translation_key = MagicMock()
        charger._get_entity_state = MagicMock()
        charger._get_onoff_switch_entity_id = MagicMock(return_value=ONOFF_ENTITY_ID)
        return charger


# --------------------------------------------------------------------------- #
# is_charger_device
# --------------------------------------------------------------------------- #
def test_is_charger_device_true_lowercase():
    """ZHA device with the lowercase manufacturer is recognised."""
    device = _make_device_entry(manufacturer=CHARGER_MANUFACTURER_AMINA_ZHA)
    assert AminaZhaCharger.is_charger_device(device) is True


def test_is_charger_device_true_capitalised():
    """ZHA device with the capitalised manufacturer is recognised."""
    device = _make_device_entry(manufacturer=CHARGER_MANUFACTURER_AMINA)
    assert AminaZhaCharger.is_charger_device(device) is True


def test_is_charger_device_wrong_domain():
    """Non-ZHA domain is rejected (e.g. the MQTT/Z2M variant)."""
    device = _make_device_entry(domain="mqtt")
    assert AminaZhaCharger.is_charger_device(device) is False


def test_is_charger_device_wrong_manufacturer():
    """ZHA device from another manufacturer is rejected."""
    device = _make_device_entry(manufacturer="Some Other Brand")
    assert AminaZhaCharger.is_charger_device(device) is False


def test_is_charger_device_no_manufacturer():
    """A missing manufacturer string does not raise and is rejected."""
    device = _make_device_entry(manufacturer=None)
    assert AminaZhaCharger.is_charger_device(device) is False


# --------------------------------------------------------------------------- #
# on/off switch resolution
# --------------------------------------------------------------------------- #
def test_get_onoff_switch_entity_id(amina_zha_charger):
    """The OnOff switch is resolved by its '-10-6' unique_id suffix."""
    amina_zha_charger._get_onoff_switch_entity_id = (
        AminaZhaCharger._get_onoff_switch_entity_id.__get__(amina_zha_charger)
    )
    onoff = MagicMock()
    onoff.domain = "switch"
    onoff.unique_id = f"00:0d:6f{AMINA_ZHA_ONOFF_UNIQUE_ID_SUFFIX}"
    onoff.entity_id = ONOFF_ENTITY_ID
    single_phase = MagicMock()
    single_phase.domain = "switch"
    single_phase.unique_id = "00:0d:6f-10-65255-single_phase"
    single_phase.entity_id = "switch.amina_s_single_phase"
    amina_zha_charger.entities = [single_phase, onoff]

    assert amina_zha_charger._get_onoff_switch_entity_id() == ONOFF_ENTITY_ID


def test_get_onoff_switch_entity_id_missing(amina_zha_charger):
    """A missing OnOff switch raises ValueError."""
    amina_zha_charger._get_onoff_switch_entity_id = (
        AminaZhaCharger._get_onoff_switch_entity_id.__get__(amina_zha_charger)
    )
    amina_zha_charger.entities = []
    with pytest.raises(ValueError, match="on/off switch"):
        amina_zha_charger._get_onoff_switch_entity_id()


# --------------------------------------------------------------------------- #
# set_phase_mode
# --------------------------------------------------------------------------- #
async def test_set_phase_mode_single(amina_zha_charger, mock_hass):
    """Single-phase mode turns the single_phase switch on."""
    amina_zha_charger._get_entity_id_by_translation_key.return_value = (
        "switch.amina_s_single_phase"
    )
    await amina_zha_charger.set_phase_mode(PhaseMode.SINGLE)
    mock_hass.services.async_call.assert_called_once_with(
        domain="switch",
        service="turn_on",
        service_data={"entity_id": "switch.amina_s_single_phase"},
        blocking=True,
    )


async def test_set_phase_mode_multi(amina_zha_charger, mock_hass):
    """Multi-phase mode turns the single_phase switch off."""
    amina_zha_charger._get_entity_id_by_translation_key.return_value = (
        "switch.amina_s_single_phase"
    )
    await amina_zha_charger.set_phase_mode(PhaseMode.MULTI)
    mock_hass.services.async_call.assert_called_once_with(
        domain="switch",
        service="turn_off",
        service_data={"entity_id": "switch.amina_s_single_phase"},
        blocking=True,
    )


async def test_set_phase_mode_invalid(amina_zha_charger):
    """An invalid phase mode raises ValueError."""
    with pytest.raises(ValueError, match="Invalid mode"):
        await amina_zha_charger.set_phase_mode("invalid_mode")


# --------------------------------------------------------------------------- #
# set_current_limit
# --------------------------------------------------------------------------- #
async def test_set_current_limit_normal(amina_zha_charger, mock_hass):
    """Above the minimum: set the charge_limit number, then turn ON."""
    amina_zha_charger._get_entity_id_by_translation_key.return_value = (
        "number.amina_s_charge_limit"
    )
    await amina_zha_charger.set_current_limit(
        {Phase.L1: 16, Phase.L2: 14, Phase.L3: 15}
    )

    mock_hass.services.async_call.assert_any_call(
        domain="number",
        service="set_value",
        service_data={"entity_id": "number.amina_s_charge_limit", "value": 14},
        blocking=True,
    )
    mock_hass.services.async_call.assert_any_call(
        domain="switch",
        service="turn_on",
        service_data={"entity_id": ONOFF_ENTITY_ID},
        blocking=True,
    )
    assert amina_zha_charger._paused is False


async def test_set_current_limit_clamps_max(amina_zha_charger, mock_hass):
    """Requests above the hardware max are clamped."""
    amina_zha_charger._get_entity_id_by_translation_key.return_value = (
        "number.amina_s_charge_limit"
    )
    await amina_zha_charger.set_current_limit(dict.fromkeys(Phase, 40))

    mock_hass.services.async_call.assert_any_call(
        domain="number",
        service="set_value",
        service_data={
            "entity_id": "number.amina_s_charge_limit",
            "value": AMINA_HW_MAX_CURRENT,
        },
        blocking=True,
    )


async def test_set_current_limit_below_min_turns_off(amina_zha_charger, mock_hass):
    """Below the 6A minimum the charger is paused via the OnOff switch."""
    await amina_zha_charger.set_current_limit(dict.fromkeys(Phase, 4))

    mock_hass.services.async_call.assert_called_once_with(
        domain="switch",
        service="turn_off",
        service_data={"entity_id": ONOFF_ENTITY_ID},
        blocking=True,
    )
    assert amina_zha_charger._paused is True


async def test_set_current_limit_empty_turns_off(amina_zha_charger, mock_hass):
    """An empty limit dict pauses the charger."""
    await amina_zha_charger.set_current_limit({})
    mock_hass.services.async_call.assert_called_once_with(
        domain="switch",
        service="turn_off",
        service_data={"entity_id": ONOFF_ENTITY_ID},
        blocking=True,
    )


# --------------------------------------------------------------------------- #
# get_current_limit
# --------------------------------------------------------------------------- #
def test_get_current_limit_uniform(amina_zha_charger):
    """The limit is reported uniformly across all phases (synced limits)."""
    amina_zha_charger._paused = False
    amina_zha_charger._get_entity_state_by_translation_key.return_value = "16"
    assert amina_zha_charger.get_current_limit() == dict.fromkeys(Phase, 16)


def test_get_current_limit_single_phase_still_uniform(amina_zha_charger):
    """Even in single-phase mode the limit is reported uniformly.

    Reporting 0 on the unused phases would make min() always 0, which stops the
    balancer from ever detecting a change for a synced-phase charger.
    """
    amina_zha_charger._paused = False
    amina_zha_charger._get_entity_state_by_translation_key.return_value = "16"
    result = amina_zha_charger.get_current_limit()
    assert result == dict.fromkeys(Phase, 16)
    assert min(result.values()) == 16


def test_get_current_limit_paused(amina_zha_charger):
    """While paused the limit is reported as zero without reading entities."""
    amina_zha_charger._paused = True
    assert amina_zha_charger.get_current_limit() == dict.fromkeys(Phase, 0)


def test_get_current_limit_missing(amina_zha_charger):
    """A missing charge_limit entity returns None."""
    amina_zha_charger._paused = False
    amina_zha_charger._get_entity_state_by_translation_key.return_value = None
    assert amina_zha_charger.get_current_limit() is None


# --------------------------------------------------------------------------- #
# get_max_current_limit
# --------------------------------------------------------------------------- #
def test_get_max_current_limit_from_sensor(amina_zha_charger):
    """The hardware_current_limit sensor drives the max limit."""
    amina_zha_charger._get_entity_state_by_translation_key.return_value = "20"
    assert amina_zha_charger.get_max_current_limit() == dict.fromkeys(Phase, 20)


def test_get_max_current_limit_fallback_none(amina_zha_charger):
    """A None sensor state falls back to the hardware maximum."""
    amina_zha_charger._get_entity_state_by_translation_key.return_value = None
    assert amina_zha_charger.get_max_current_limit() == dict.fromkeys(
        Phase, AMINA_HW_MAX_CURRENT
    )


def test_get_max_current_limit_fallback_missing_entity(amina_zha_charger):
    """A missing sensor entity (ValueError) falls back to the hardware maximum."""
    amina_zha_charger._get_entity_state_by_translation_key.side_effect = ValueError
    assert amina_zha_charger.get_max_current_limit() == dict.fromkeys(
        Phase, AMINA_HW_MAX_CURRENT
    )


# --------------------------------------------------------------------------- #
# status methods
# --------------------------------------------------------------------------- #
def test_car_connected_true(amina_zha_charger):
    """car_connected reflects the ev_connected binary sensor."""
    amina_zha_charger._get_entity_state_by_translation_key.return_value = STATE_ON
    assert amina_zha_charger.car_connected() is True


def test_car_connected_false(amina_zha_charger):
    """car_connected is False when the binary sensor is off/unknown."""
    for state in (STATE_OFF, None):
        amina_zha_charger._get_entity_state_by_translation_key.return_value = state
        assert amina_zha_charger.car_connected() is False


def test_is_charging_true(amina_zha_charger):
    """is_charging reflects the charging binary sensor."""
    amina_zha_charger._get_entity_state_by_translation_key.return_value = STATE_ON
    assert amina_zha_charger.is_charging() is True


def test_is_charging_false(amina_zha_charger):
    """is_charging is False when the binary sensor is off/unknown."""
    for state in (STATE_OFF, None):
        amina_zha_charger._get_entity_state_by_translation_key.return_value = state
        assert amina_zha_charger.is_charging() is False


def test_can_charge_true(amina_zha_charger):
    """can_charge is True for charging/ready/connected statuses."""
    for status in ("Charging", "Ready to charge", "EV connected", "Charging (derated)"):

        def _state(key, status=status):
            return {
                AminaZhaEntityMap.EvConnected: STATE_ON,
                AminaZhaEntityMap.EvStatus: status,
            }[key]

        amina_zha_charger._get_entity_state_by_translation_key.side_effect = _state
        assert amina_zha_charger.can_charge() is True


def test_can_charge_false_when_disconnected(amina_zha_charger):
    """can_charge is False when the car is not connected."""
    amina_zha_charger._get_entity_state_by_translation_key.return_value = STATE_OFF
    assert amina_zha_charger.can_charge() is False


def test_can_charge_false_when_paused(amina_zha_charger):
    """can_charge is False for a connected-but-paused car."""

    def _state(key):
        return {
            AminaZhaEntityMap.EvConnected: STATE_ON,
            AminaZhaEntityMap.EvStatus: "Paused",
        }[key]

    amina_zha_charger._get_entity_state_by_translation_key.side_effect = _state
    assert amina_zha_charger.can_charge() is False


def test_has_synced_phase_limits(amina_zha_charger):
    """The Amina S always reports synced phase limits."""
    assert amina_zha_charger.has_synced_phase_limits() is True


async def test_async_setup_and_unload(amina_zha_charger):
    """async_setup/async_unload are no-ops and must not raise."""
    await amina_zha_charger.async_setup()
    await amina_zha_charger.async_unload()
