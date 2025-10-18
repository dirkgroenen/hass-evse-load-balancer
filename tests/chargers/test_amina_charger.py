import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from custom_components.evse_load_balancer.const import (
    Phase,
    CHARGER_MANUFACTURER_AMINA,
    HA_INTEGRATION_DOMAIN_MQTT,
    Z2M_DEVICE_IDENTIFIER_DOMAIN
)
from homeassistant.helpers.device_registry import DeviceEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry
from custom_components.evse_load_balancer.chargers.amina_charger import (
    AminaCharger,
    AminaPropertyMap,
    AminaStatusMap,
    AMINA_HW_MAX_CURRENT,
)

from custom_components.evse_load_balancer.chargers.charger import (
    PhaseMode
)


def _make_device_entry(
        id="test_device_id",
        domain=HA_INTEGRATION_DOMAIN_MQTT,
        prefix=Z2M_DEVICE_IDENTIFIER_DOMAIN + "_amina",
        manufacturer=CHARGER_MANUFACTURER_AMINA
) -> MagicMock:
    device_entry = MagicMock(spec=DeviceEntry)
    device_entry.id = id
    device_entry.identifiers = {(domain, prefix)}
    device_entry.manufacturer = manufacturer
    return device_entry


@pytest.fixture
def config_entry():
    """Create a mock ConfigEntry for the tests."""
    return MockConfigEntry(
        domain="evse_load_balancer",
        title="Amina Test Charger",
        data={"charger_type": "amina"},
        unique_id="test_amina_charger",
    )


@pytest.fixture
def device_entry():
    """Create a mock DeviceEntry object for testing."""
    return _make_device_entry(
        domain=HA_INTEGRATION_DOMAIN_MQTT,
        prefix=Z2M_DEVICE_IDENTIFIER_DOMAIN + "_amina",
        manufacturer=CHARGER_MANUFACTURER_AMINA
    )


@pytest.fixture
def amina_charger(hass, config_entry, device_entry):
    return AminaCharger(hass, config_entry, device_entry)


def test_correct_gettable_prop_initialization(amina_charger):
    assert amina_charger._gettable_properties == ["charge_limit", "single_phase"]


def test_is_charger_device_true():
    device_entry = _make_device_entry(
        domain=HA_INTEGRATION_DOMAIN_MQTT,
        prefix=Z2M_DEVICE_IDENTIFIER_DOMAIN + "_amina",
        manufacturer=CHARGER_MANUFACTURER_AMINA
    )
    assert AminaCharger.is_charger_device(device_entry) is True


def test_is_charger_device_wrong_domain():
    device_entry = _make_device_entry(
        domain="other_domain"
    )
    assert AminaCharger.is_charger_device(device_entry) is False


def test_is_charger_device_wrong_prefix():
    device_entry = _make_device_entry(
        prefix="some_prefix"
    )
    assert AminaCharger.is_charger_device(device_entry) is False


def test_is_charger_device_wrong_manufacturer():
    device_entry = _make_device_entry(
        prefix="apples"
    )
    assert AminaCharger.is_charger_device(device_entry) is False


def test_get_current_limit_three_phase(amina_charger):
    amina_charger._state_cache[AminaPropertyMap.ChargeLimit] = 16
    amina_charger._state_cache[AminaPropertyMap.SinglePhase] = False
    result = amina_charger.get_current_limit()
    assert result == {Phase.L1: 16, Phase.L2: 16, Phase.L3: 16}


def test_get_current_limit_single_phase(amina_charger):
    amina_charger._state_cache[AminaPropertyMap.ChargeLimit] = 10
    amina_charger._state_cache[AminaPropertyMap.SinglePhase] = True
    result = amina_charger.get_current_limit()
    assert result == {Phase.L1: 10, Phase.L2: 0, Phase.L3: 0}


def test_get_max_current_limit(amina_charger):
    result = amina_charger.get_max_current_limit()
    assert result == {Phase.L1: AMINA_HW_MAX_CURRENT, Phase.L2: AMINA_HW_MAX_CURRENT, Phase.L3: AMINA_HW_MAX_CURRENT}


def test_car_connected_true(amina_charger):
    amina_charger._state_cache[AminaPropertyMap.EvConnected] = True
    assert amina_charger.car_connected() is True


def test_car_connected_false(amina_charger):
    amina_charger._state_cache[AminaPropertyMap.EvConnected] = False
    assert amina_charger.car_connected() is False


def test_is_charging_true(amina_charger):
    amina_charger._state_cache[AminaPropertyMap.Charging] = True
    assert amina_charger.is_charging() is True


def test_is_charging_false(amina_charger):
    amina_charger._state_cache[AminaPropertyMap.EvConnected] = False
    assert amina_charger.is_charging() is False


def test_can_charge_false_not_connected(amina_charger):
    amina_charger._state_cache[AminaPropertyMap.EvConnected] = False
    assert amina_charger.can_charge() is False


def test_can_charge_true_charging(amina_charger):
    amina_charger._state_cache[AminaPropertyMap.EvConnected] = True
    amina_charger._state_cache[AminaPropertyMap.EvStatus] = AminaStatusMap.Charging
    assert amina_charger.can_charge() is True


def test_can_charge_true_ready(amina_charger):
    amina_charger._state_cache[AminaPropertyMap.EvConnected] = True
    amina_charger._state_cache[AminaPropertyMap.EvStatus] = AminaStatusMap.ReadyToCharge
    assert amina_charger.can_charge() is True


def test_can_charge_false_other_status(amina_charger):
    amina_charger._state_cache[AminaPropertyMap.EvConnected] = True
    amina_charger._state_cache[AminaPropertyMap.EvStatus] = "not_ready"
    assert amina_charger.can_charge() is False


@pytest.mark.asyncio
async def test_set_phase_mode_single(amina_charger):
    with patch.object(amina_charger, "_async_mqtt_publish", new=AsyncMock()) as mock_publish:
        await amina_charger.set_phase_mode(PhaseMode.SINGLE)
        mock_publish.assert_awaited_once_with(
            topic=amina_charger._topic_set,
            payload={AminaPropertyMap.SinglePhase: "enable"}
        )


@pytest.mark.asyncio
async def test_set_phase_mode_three(amina_charger):
    with patch.object(amina_charger, "_async_mqtt_publish", new=AsyncMock()) as mock_publish:
        await amina_charger.set_phase_mode(PhaseMode.MULTI)
        mock_publish.assert_awaited_once_with(
            topic=amina_charger._topic_set,
            payload={AminaPropertyMap.SinglePhase: "disable"}
        )


@pytest.mark.asyncio
async def test_set_current_limit(amina_charger):
    with patch.object(amina_charger, "_async_mqtt_publish", new=AsyncMock()) as mock_publish:
        await amina_charger.set_current_limit({Phase.L1: 20, Phase.L2: 18, Phase.L3: 15})
        mock_publish.assert_awaited_once_with(
            topic=amina_charger._topic_set,
            payload={AminaPropertyMap.ChargeLimit: 15}
        )


@pytest.mark.asyncio
async def test_async_setup(amina_charger):
    with patch.object(amina_charger, "async_setup_mqtt", new=AsyncMock()) as mock_setup:
        await amina_charger.async_setup()
        mock_setup.assert_awaited_once()


@pytest.mark.asyncio
async def test_async_unload(amina_charger):
    with patch.object(amina_charger, "async_unload_mqtt", new=AsyncMock()) as mock_unload:
        await amina_charger.async_unload()
        mock_unload.assert_awaited_once()
