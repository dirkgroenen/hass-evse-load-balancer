"""Tests for the OCPP charger implementation."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import RegistryEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evse_load_balancer.chargers.charger import PhaseMode
from custom_components.evse_load_balancer.chargers.ocpp_charger import (
    OCPP_CAR_MIN_CURRENT,
    OCPP_HW_MAX_CURRENT,
    OcppCharger,
    OcppEntityMap,
    OcppStatusMap,
)
from custom_components.evse_load_balancer.const import CHARGER_DOMAIN_OCPP
from custom_components.evse_load_balancer.meters.meter import Phase


def _registry_entry(*, entity_id: str, unique_id: str, domain: str) -> MagicMock:
    """Build a mock RegistryEntry with the OCPP-style dot-separated unique_id."""
    entry = MagicMock(spec=RegistryEntry)
    entry.entity_id = entity_id
    entry.unique_id = unique_id
    entry.domain = domain
    entry.disabled = False
    return entry


@pytest.fixture
def mock_hass():
    """Create a mock HomeAssistant instance for testing."""
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()
    hass.states = MagicMock()
    return hass


@pytest.fixture
def mock_config_entry():
    """Create a mock ConfigEntry for the tests."""
    return MockConfigEntry(
        domain="evse_load_balancer",
        title="OCPP Test Charger",
        data={"charger_type": "ocpp"},
        unique_id="test_ocpp_charger",
    )


@pytest.fixture
def mock_device_entry():
    """Create a mock DeviceEntry object for testing."""
    device_entry = MagicMock(spec=DeviceEntry)
    device_entry.id = "test_device_id"
    device_entry.name = "test_charger"
    device_entry.identifiers = {(CHARGER_DOMAIN_OCPP, "test_charger")}
    return device_entry


@pytest.fixture
def ocpp_entities():
    """Build a realistic set of OCPP entities for a single-connector charger.

    The unique-ids use dot-separated parts -- this is what makes OCPP
    different from the other chargers and what `_get_ocpp_entity_id`
    has to handle correctly.
    """
    return [
        _registry_entry(
            entity_id="number.test_charger_maximum_current",
            unique_id="number.ocpp.test_charger.maximum_current",
            domain="number",
        ),
        _registry_entry(
            entity_id="switch.test_charger_charge_control",
            unique_id="switch.ocpp.test_charger.charge_control",
            domain="switch",
        ),
        _registry_entry(
            entity_id="sensor.test_charger_status_connector",
            unique_id="ocpp.test_charger.status_connector.sensor",
            domain="sensor",
        ),
        _registry_entry(
            entity_id="sensor.test_charger_status",
            unique_id="ocpp.test_charger.status.sensor",
            domain="sensor",
        ),
    ]


@pytest.fixture
def ocpp_charger(mock_hass, mock_config_entry, mock_device_entry, ocpp_entities):
    """Create an OcppCharger instance for testing.

    The ``__init__`` of OcppCharger emits a discovery-log line that calls
    ``_get_ocpp_entity_id`` which reads ``self.entities``. We make
    ``refresh_entities`` patch in the test entities so that initialisation
    completes cleanly and the rest of the lookups in tests work against
    those entities too.
    """

    def _refresh_entities(self):
        self.entities = list(ocpp_entities)

    with patch(
        "custom_components.evse_load_balancer.chargers.ocpp_charger.OcppCharger.refresh_entities",
        autospec=True,
        side_effect=_refresh_entities,
    ):
        charger = OcppCharger(
            hass=mock_hass,
            config_entry=mock_config_entry,
            device_entry=mock_device_entry,
        )
        # Stub the generic state-reader the parent class provides. Individual
        # tests override the return value as needed.
        charger._get_entity_state = MagicMock()
        charger._get_entity_state_attrs = MagicMock(return_value={})
        return charger


# ---------------------------------------------------------------------------
# Device-detection
# ---------------------------------------------------------------------------


def test_is_charger_device_true(mock_device_entry):
    """Test is_charger_device returns True for OCPP devices."""
    mock_device_entry.identifiers = {(CHARGER_DOMAIN_OCPP, "test_charger")}
    assert OcppCharger.is_charger_device(mock_device_entry) is True


def test_is_charger_device_multi_connector(mock_device_entry):
    """Test is_charger_device matches multi-connector device identifiers."""
    mock_device_entry.identifiers = {(CHARGER_DOMAIN_OCPP, "test_charger-conn1")}
    assert OcppCharger.is_charger_device(mock_device_entry) is True


def test_is_charger_device_false():
    """Test is_charger_device returns False for non-OCPP devices."""
    mock_device_entry = MagicMock(spec=DeviceEntry)
    mock_device_entry.identifiers = {("other_domain", "test_charger")}
    assert OcppCharger.is_charger_device(mock_device_entry) is False


# ---------------------------------------------------------------------------
# Dot-aware entity lookup -- the load-bearing part of the OCPP backend.
# ---------------------------------------------------------------------------


def test_get_ocpp_entity_id_finds_number(ocpp_charger):
    """The lookup helper finds the maximum_current number entity by key."""
    result = ocpp_charger._get_ocpp_entity_id(
        domain="number", key=OcppEntityMap.MaximumCurrent
    )
    assert result == "number.test_charger_maximum_current"


def test_get_ocpp_entity_id_finds_switch(ocpp_charger):
    """The lookup helper finds the charge_control switch by key."""
    result = ocpp_charger._get_ocpp_entity_id(
        domain="switch", key=OcppEntityMap.ChargeControl
    )
    assert result == "switch.test_charger_charge_control"


def test_get_ocpp_entity_id_finds_status_connector_sensor(ocpp_charger):
    """The lookup helper finds the dot-separated connector status sensor."""
    result = ocpp_charger._get_ocpp_entity_id(
        domain="sensor", key=OcppEntityMap.StatusConnector
    )
    assert result == "sensor.test_charger_status_connector"


def test_get_ocpp_entity_id_returns_none_when_missing(ocpp_charger):
    """The lookup helper returns None for unknown keys."""
    result = ocpp_charger._get_ocpp_entity_id(domain="number", key="bogus_key")
    assert result is None


def test_get_ocpp_entity_id_multi_connector_unique_id(
    mock_hass, mock_config_entry, mock_device_entry
):
    """The lookup helper handles multi-connector unique-ids correctly.

    Multi-connector OCPP entities have an extra ``conn<N>`` part inserted
    in the dot-separated unique-id (e.g.
    ``number.ocpp.<cpid>.conn1.maximum_current``). The key still appears
    as one of the dot parts so the lookup should still match.
    """
    multi_conn_entity = _registry_entry(
        entity_id="number.test_charger_conn1_maximum_current",
        unique_id="number.ocpp.test_charger.conn1.maximum_current",
        domain="number",
    )

    def _refresh_entities(self):
        self.entities = [multi_conn_entity]

    with patch(
        "custom_components.evse_load_balancer.chargers.ocpp_charger.OcppCharger.refresh_entities",
        autospec=True,
        side_effect=_refresh_entities,
    ):
        charger = OcppCharger(
            hass=mock_hass,
            config_entry=mock_config_entry,
            device_entry=mock_device_entry,
        )

    result = charger._get_ocpp_entity_id(
        domain="number", key=OcppEntityMap.MaximumCurrent
    )
    assert result == "number.test_charger_conn1_maximum_current"


# ---------------------------------------------------------------------------
# Phase mode: OCPP 1.6 cannot toggle phases, so this is a validated no-op.
# ---------------------------------------------------------------------------


def test_set_phase_mode_accepts_single(ocpp_charger):
    """set_phase_mode accepts single without error (no-op for OCPP 1.6)."""
    ocpp_charger.set_phase_mode(PhaseMode.SINGLE)


def test_set_phase_mode_accepts_multi(ocpp_charger):
    """set_phase_mode accepts multi without error (no-op for OCPP 1.6)."""
    ocpp_charger.set_phase_mode(PhaseMode.MULTI)


def test_set_phase_mode_invalid_raises(ocpp_charger):
    """set_phase_mode raises ValueError for invalid modes."""
    with pytest.raises(ValueError, match="Invalid mode"):
        ocpp_charger.set_phase_mode("not_a_real_mode")


# ---------------------------------------------------------------------------
# Current-limit application (normal range, clamping, availability defence)
# ---------------------------------------------------------------------------


async def test_set_current_limit_normal_value(ocpp_charger, mock_hass):
    """Setting a current >=6A pushes it directly to the OCPP number entity."""
    mock_hass.states.get = MagicMock(return_value=MagicMock(state="16.0"))
    ocpp_charger._get_entity_state.return_value = OcppStatusMap.Charging

    await ocpp_charger.set_current_limit({Phase.L1: 12, Phase.L2: 12, Phase.L3: 12})

    mock_hass.services.async_call.assert_called_once_with(
        domain="number",
        service="set_value",
        service_data={
            "entity_id": "number.test_charger_maximum_current",
            "value": 12,
        },
        blocking=True,
    )


async def test_set_current_limit_uses_lowest_phase(ocpp_charger, mock_hass):
    """OCPP exposes one charge-point-wide limit so we use the lowest phase."""
    mock_hass.states.get = MagicMock(return_value=MagicMock(state="16.0"))
    ocpp_charger._get_entity_state.return_value = OcppStatusMap.Charging

    await ocpp_charger.set_current_limit({Phase.L1: 16, Phase.L2: 10, Phase.L3: 14})

    call_value = mock_hass.services.async_call.call_args.kwargs["service_data"]["value"]
    assert call_value == 10


async def test_set_current_limit_clamps_to_hw_max(ocpp_charger, mock_hass):
    """Above-hardware-max requests are clamped to OCPP_HW_MAX_CURRENT."""
    mock_hass.states.get = MagicMock(return_value=MagicMock(state="32.0"))
    ocpp_charger._get_entity_state.return_value = OcppStatusMap.Charging

    await ocpp_charger.set_current_limit({Phase.L1: 50, Phase.L2: 50, Phase.L3: 50})

    call_value = mock_hass.services.async_call.call_args.kwargs["service_data"]["value"]
    assert call_value == OCPP_HW_MAX_CURRENT


async def test_set_current_limit_aborts_on_unavailable_entity(
    ocpp_charger, mock_hass
):
    """When the OCPP number entity is unavailable, no service call is made.

    This is the SmartCharging-feature-profile defence: cheap chargers
    that do not advertise SmartCharging expose ``maximum_current`` as
    unavailable, and pushing to it silently no-ops. We must refuse
    instead so the user gets a clear error.
    """
    mock_hass.states.get = MagicMock(return_value=MagicMock(state="unavailable"))

    await ocpp_charger.set_current_limit({Phase.L1: 12, Phase.L2: 12, Phase.L3: 12})

    mock_hass.services.async_call.assert_not_called()


# ---------------------------------------------------------------------------
# IEC 61851 pause and resume -- the trickiest part of the OCPP backend.
# ---------------------------------------------------------------------------


async def test_set_current_limit_snaps_below_min_to_zero(ocpp_charger, mock_hass):
    """Sub-6A requests are snapped to 0A (pause)."""
    mock_hass.states.get = MagicMock(return_value=MagicMock(state="16.0"))
    ocpp_charger._get_entity_state.return_value = OcppStatusMap.Charging

    await ocpp_charger.set_current_limit({Phase.L1: 4, Phase.L2: 4, Phase.L3: 4})

    # Snap to 0A, no kick (we are entering pause, not leaving it).
    mock_hass.services.async_call.assert_called_once_with(
        domain="number",
        service="set_value",
        service_data={
            "entity_id": "number.test_charger_maximum_current",
            "value": 0,
        },
        blocking=True,
    )


async def test_set_current_limit_remembers_pre_snap_value(ocpp_charger, mock_hass):
    """The pre-snap value is stored so the override detector doesn't trip.

    Without this, the upstream allocator's manual-override detector
    compares the slider (0A after snap) against ``last_applied_current``
    (the pre-snap 4A), sees a mismatch and adopts 0A as the new
    ceiling -- permanently locking the charger off.
    """
    mock_hass.states.get = MagicMock(return_value=MagicMock(state="16.0"))
    ocpp_charger._get_entity_state.return_value = OcppStatusMap.Charging

    limit = {Phase.L1: 4, Phase.L2: 4, Phase.L3: 4}
    await ocpp_charger.set_current_limit(limit)

    assert ocpp_charger._last_requested == limit


async def test_set_current_limit_kicks_switch_on_resume(ocpp_charger, mock_hass):
    """A >=6A request while paused triggers the charge_control kick.

    OCPP 1.6 profile replacement alone does not re-energise the contactor
    on many chargers; they wait for a fresh RemoteStartTransaction. We
    push the new profile first, then toggle the switch off->on to force
    a transaction restart.
    """
    mock_hass.states.get = MagicMock(return_value=MagicMock(state="0.0"))
    ocpp_charger._get_entity_state.return_value = OcppStatusMap.SuspendedEVSE

    await ocpp_charger.set_current_limit({Phase.L1: 10, Phase.L2: 10, Phase.L3: 10})

    # Expect three service calls in order: set the new profile (10A), then
    # turn the switch off (RemoteStop), then back on (RemoteStart).
    calls = mock_hass.services.async_call.call_args_list
    assert len(calls) == 3
    assert calls[0].kwargs == {
        "domain": "number",
        "service": "set_value",
        "service_data": {
            "entity_id": "number.test_charger_maximum_current",
            "value": 10,
        },
        "blocking": True,
    }
    assert calls[1].kwargs["service"] == "turn_off"
    assert calls[1].kwargs["service_data"] == {
        "entity_id": "switch.test_charger_charge_control"
    }
    assert calls[2].kwargs["service"] == "turn_on"
    assert calls[2].kwargs["service_data"] == {
        "entity_id": "switch.test_charger_charge_control"
    }


async def test_set_current_limit_no_kick_when_already_charging(
    ocpp_charger, mock_hass
):
    """No kick when the charger is already Charging -- just push the value."""
    mock_hass.states.get = MagicMock(return_value=MagicMock(state="16.0"))
    ocpp_charger._get_entity_state.return_value = OcppStatusMap.Charging

    await ocpp_charger.set_current_limit({Phase.L1: 10, Phase.L2: 10, Phase.L3: 10})

    # Only one call: set the new profile. No switch toggle.
    assert mock_hass.services.async_call.call_count == 1
    assert mock_hass.services.async_call.call_args.kwargs["domain"] == "number"


# ---------------------------------------------------------------------------
# get_current_limit -- including the paused-state lie
# ---------------------------------------------------------------------------


def test_get_current_limit_normal(ocpp_charger):
    """Normal path: reads the real slider value."""
    ocpp_charger._get_entity_state.return_value = 14.0

    result = ocpp_charger.get_current_limit()

    assert result == {Phase.L1: 14, Phase.L2: 14, Phase.L3: 14}


def test_get_current_limit_paused_returns_last_requested(ocpp_charger):
    """While paused, get_current_limit reports the last requested value.

    This prevents the upstream manual-override detector from seeing a
    discrepancy between the real 0A slider and the allocator's
    ``last_applied_current`` (which holds the pre-snap value).
    """
    # Simulate having paused at 4A previously.
    ocpp_charger._last_requested = {Phase.L1: 4, Phase.L2: 4, Phase.L3: 4}

    # Real slider is at 0A; status is SuspendedEVSE.
    def _state_side_effect(entity_id, parser_fn=None):
        if entity_id == "number.test_charger_maximum_current":
            return 0.0
        return OcppStatusMap.SuspendedEVSE

    ocpp_charger._get_entity_state.side_effect = _state_side_effect

    result = ocpp_charger.get_current_limit()

    # Reports the pre-snap value, not the real 0A.
    assert result == {Phase.L1: 4, Phase.L2: 4, Phase.L3: 4}


def test_get_current_limit_paused_without_last_requested(ocpp_charger):
    """If we are paused but have no _last_requested, fall back to real value.

    Defensive: should only happen on a fresh integration load where the
    charger was already paused before we started.
    """
    ocpp_charger._last_requested = None

    def _state_side_effect(entity_id, parser_fn=None):
        if entity_id == "number.test_charger_maximum_current":
            return 0.0
        return OcppStatusMap.SuspendedEVSE

    ocpp_charger._get_entity_state.side_effect = _state_side_effect

    result = ocpp_charger.get_current_limit()
    assert result == {Phase.L1: 0, Phase.L2: 0, Phase.L3: 0}


# ---------------------------------------------------------------------------
# get_max_current_limit -- reads max attribute, falls back gracefully
# ---------------------------------------------------------------------------


def test_get_max_current_limit_from_entity_attribute(ocpp_charger):
    """Max is read from the OCPP number entity's `max` attribute."""
    ocpp_charger._get_entity_state_attrs.return_value = {"max": 32.0}

    result = ocpp_charger.get_max_current_limit()

    assert result == {Phase.L1: 32, Phase.L2: 32, Phase.L3: 32}


def test_get_max_current_limit_fallback_when_missing(ocpp_charger):
    """Falls back to the hardware default when the attribute is missing."""
    ocpp_charger._get_entity_state_attrs.return_value = {}

    result = ocpp_charger.get_max_current_limit()

    assert result == {
        Phase.L1: OCPP_HW_MAX_CURRENT,
        Phase.L2: OCPP_HW_MAX_CURRENT,
        Phase.L3: OCPP_HW_MAX_CURRENT,
    }


# ---------------------------------------------------------------------------
# Synced-phase flag (OCPP only has one charge-point-wide setting)
# ---------------------------------------------------------------------------


def test_has_synced_phase_limits(ocpp_charger):
    """OCPP always reports synced phase limits."""
    assert ocpp_charger.has_synced_phase_limits() is True


# ---------------------------------------------------------------------------
# Status-based predicates (car_connected, can_charge, is_charging)
# ---------------------------------------------------------------------------


def test_car_connected_true(ocpp_charger):
    """car_connected returns True for any plug-in state."""
    for status in [
        OcppStatusMap.Preparing,
        OcppStatusMap.Charging,
        OcppStatusMap.SuspendedEVSE,
        OcppStatusMap.SuspendedEV,
        OcppStatusMap.Finishing,
    ]:
        ocpp_charger._get_entity_state.return_value = status
        assert ocpp_charger.car_connected() is True


def test_car_connected_false(ocpp_charger):
    """car_connected returns False when there is no plugged car."""
    for status in [
        OcppStatusMap.Available,
        OcppStatusMap.Reserved,
        OcppStatusMap.Unavailable,
        OcppStatusMap.Faulted,
        None,
    ]:
        ocpp_charger._get_entity_state.return_value = status
        assert ocpp_charger.car_connected() is False


def test_can_charge_true(ocpp_charger):
    """can_charge stays True through Suspended* states so the balancer keeps
    trying to allocate current and trigger a resume."""
    for status in [
        OcppStatusMap.Preparing,
        OcppStatusMap.Charging,
        OcppStatusMap.SuspendedEVSE,
        OcppStatusMap.SuspendedEV,
    ]:
        ocpp_charger._get_entity_state.return_value = status
        assert ocpp_charger.can_charge() is True


def test_can_charge_false_for_finishing(ocpp_charger):
    """can_charge is False once the connector is in Finishing."""
    ocpp_charger._get_entity_state.return_value = OcppStatusMap.Finishing
    assert ocpp_charger.can_charge() is False


def test_is_charging_only_charging(ocpp_charger):
    """is_charging is True only for the actively-charging status."""
    ocpp_charger._get_entity_state.return_value = OcppStatusMap.Charging
    assert ocpp_charger.is_charging() is True

    for status in [
        OcppStatusMap.Preparing,
        OcppStatusMap.SuspendedEVSE,
        OcppStatusMap.SuspendedEV,
        OcppStatusMap.Finishing,
        OcppStatusMap.Available,
        None,
    ]:
        ocpp_charger._get_entity_state.return_value = status
        assert ocpp_charger.is_charging() is False


# ---------------------------------------------------------------------------
# Lifecycle no-ops
# ---------------------------------------------------------------------------


async def test_async_setup(ocpp_charger):
    """async_setup is a no-op for the OCPP backend."""
    await ocpp_charger.async_setup()


async def test_async_unload(ocpp_charger):
    """async_unload is a no-op for the OCPP backend."""
    await ocpp_charger.async_unload()


def test_current_change_settle_time_overridden(ocpp_charger):
    """Settle time is overridden to 30s for OCPP (default is 15s).

    OCPP chargers only confirm a new ChargingProfile after their next
    meter-value interval (typically 30-60s).
    """
    assert ocpp_charger.current_change_settle_time == 30
