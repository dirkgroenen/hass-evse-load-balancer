"""Tests for the OCPP charger implementation."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceEntry
from homeassistant.helpers.entity_registry import RegistryEntry
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evse_load_balancer.chargers import ocpp_charger as ocpp_mod
from custom_components.evse_load_balancer.chargers.charger import PhaseMode
from custom_components.evse_load_balancer.chargers.ocpp_charger import (
    OCPP_HW_MAX_CURRENT,
    ControlLever,
    OcppCharger,
    OcppEntityMap,
    OcppStatusMap,
)
from custom_components.evse_load_balancer.const import CHARGER_DOMAIN_OCPP
from custom_components.evse_load_balancer.meters.meter import Phase

STATION = "number.test_charger_maximum_current"
SESSION = "number.test_charger_session_current_limit"
SWITCH = "switch.test_charger_charge_control"
STATUS_CONN = "sensor.test_charger_status_connector"
STATUS = "sensor.test_charger_status"
TX = "sensor.test_charger_transaction_id"

MODULE = "custom_components.evse_load_balancer.chargers.ocpp_charger"


def _registry_entry(*, entity_id: str, unique_id: str, domain: str) -> MagicMock:
    """Build a mock RegistryEntry with an OCPP-style dot-separated unique_id."""
    entry = MagicMock(spec=RegistryEntry)
    entry.entity_id = entity_id
    entry.unique_id = unique_id
    entry.domain = domain
    entry.disabled = False
    return entry


def _limit(value: int) -> dict:
    return {Phase.L1: value, Phase.L2: value, Phase.L3: value}


class FakeTask:
    """Stand-in for the asyncio.Task returned by async_create_background_task."""

    def __init__(self, coro):
        self.coro = coro
        self._done = False

    def done(self):
        return self._done

    def cancel(self):
        self._done = True
        self.coro.close()


async def run_scheduled(charger):
    """Run the charger's pending background task to completion."""
    task = charger._task
    assert task is not None, "nothing was scheduled"
    await task.coro
    task._done = True


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def states():
    """Entity states keyed by entity_id; shared by hass and the charger."""
    return {
        STATION: "16",
        STATUS_CONN: OcppStatusMap.Charging,
        STATUS: OcppStatusMap.Charging,
        SWITCH: "on",
        TX: "1001",
    }


@pytest.fixture
def mock_hass(states):
    """Create a mock HomeAssistant instance backed by ``states``."""
    tasks = []

    def _create_task(coro, name):
        tasks.append(FakeTask(coro))
        return tasks[-1]

    hass = MagicMock()
    hass.states.get = lambda eid: (
        SimpleNamespace(state=states[eid]) if eid in states else None
    )
    hass.services.async_call = AsyncMock()
    hass.async_create_background_task = MagicMock(side_effect=_create_task)
    yield hass
    for task in tasks:  # close coroutines a test scheduled but never ran
        if not task.done():
            task.cancel()


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
    device_entry.via_device_id = None
    return device_entry


@pytest.fixture
def station_entities():
    """Entities of a single-connector charger on ocpp < 0.12."""
    return [
        _registry_entry(
            entity_id=STATION,
            unique_id="number.ocpp.test_charger.maximum_current",
            domain="number",
        ),
        _registry_entry(
            entity_id=SWITCH,
            unique_id="switch.ocpp.test_charger.charge_control",
            domain="switch",
        ),
        _registry_entry(
            entity_id=STATUS_CONN,
            unique_id="ocpp.test_charger.status_connector.sensor",
            domain="sensor",
        ),
        _registry_entry(
            entity_id=STATUS,
            unique_id="ocpp.test_charger.status.sensor",
            domain="sensor",
        ),
        _registry_entry(
            entity_id=TX,
            unique_id="ocpp.test_charger.transaction_id.sensor",
            domain="sensor",
        ),
    ]


@pytest.fixture
def session_entities(station_entities):
    """Entities of a single-connector charger on ocpp >= 0.12."""
    return [
        *station_entities,
        _registry_entry(
            entity_id=SESSION,
            unique_id="number.ocpp.test_charger.session_current_limit",
            domain="number",
        ),
    ]


def _build(hass, config_entry, device_entry, entities, parent_entities=()):
    def _refresh_entities(self):
        self.entities = list(entities)
        self._parent_entities = list(parent_entities)

    with patch(
        f"{MODULE}.OcppCharger.refresh_entities",
        autospec=True,
        side_effect=_refresh_entities,
    ):
        charger = OcppCharger(
            hass=hass, config_entry=config_entry, device_entry=device_entry
        )
    return charger


def _wire_states(charger, states):
    def _get_entity_state(entity_id, parser_fn=None):
        raw = states.get(entity_id)
        if raw in (None, "unknown", "unavailable"):
            return None
        if parser_fn is None:
            return raw
        try:
            return parser_fn(raw)
        except ValueError:
            return None

    charger._get_entity_state = _get_entity_state
    charger._get_entity_state_attrs = MagicMock(return_value={"max": 16})
    return charger


@pytest.fixture
def station_charger(
    mock_hass, mock_config_entry, mock_device_entry, station_entities, states
):
    """OcppCharger on ocpp < 0.12 (station lever only)."""
    charger = _build(mock_hass, mock_config_entry, mock_device_entry, station_entities)
    return _wire_states(charger, states)


@pytest.fixture
def session_charger(
    mock_hass, mock_config_entry, mock_device_entry, session_entities, states
):
    """OcppCharger on ocpp >= 0.12 (session lever, transaction running)."""
    states[SESSION] = "unknown"  # bound to a transaction, nothing set yet
    charger = _build(mock_hass, mock_config_entry, mock_device_entry, session_entities)
    return _wire_states(charger, states)


@pytest.fixture
def fast():
    """Collapse the background-task timers."""
    with (
        patch(f"{MODULE}.OCPP_RESUME_GRACE", 0),
        patch(f"{MODULE}.OCPP_SESSION_BIND_TIMEOUT", 0.2),
        patch(f"{MODULE}.OCPP_NEW_TRANSACTION_TIMEOUT", 0.2),
        patch(f"{MODULE}._POLL_INTERVAL", 0),
    ):
        yield


def _number_calls(hass):
    return [
        (c.kwargs["service_data"]["entity_id"], c.kwargs["service_data"]["value"])
        for c in hass.services.async_call.call_args_list
        if c.kwargs["domain"] == "number"
    ]


def _switch_calls(hass):
    return [
        c.kwargs["service"]
        for c in hass.services.async_call.call_args_list
        if c.kwargs["domain"] == "switch"
    ]


# ---------------------------------------------------------------------------
# Device detection
# ---------------------------------------------------------------------------


def test_is_charger_device_true(mock_device_entry):
    """OCPP devices are detected."""
    assert OcppCharger.is_charger_device(mock_device_entry) is True


def test_is_charger_device_multi_connector(mock_device_entry):
    """Multi-connector device identifiers are detected."""
    mock_device_entry.identifiers = {(CHARGER_DOMAIN_OCPP, "test_charger-conn1")}
    assert OcppCharger.is_charger_device(mock_device_entry) is True


def test_is_charger_device_false():
    """Non-OCPP devices are not detected."""
    device = MagicMock(spec=DeviceEntry)
    device.identifiers = {("other_domain", "test_charger")}
    assert OcppCharger.is_charger_device(device) is False


# ---------------------------------------------------------------------------
# Dot-aware entity lookup
# ---------------------------------------------------------------------------


def test_lookup_station_number(station_charger):
    """maximum_current is found by its dot-separated key."""
    assert (
        station_charger._get_ocpp_entity_id(
            domain="number", key=OcppEntityMap.MaximumCurrent
        )
        == STATION
    )


def test_lookup_switch_and_status(station_charger):
    """Switch and connector status sensor are found."""
    assert (
        station_charger._get_ocpp_entity_id(
            domain="switch", key=OcppEntityMap.ChargeControl
        )
        == SWITCH
    )
    assert (
        station_charger._get_ocpp_entity_id(
            domain="sensor", key=OcppEntityMap.StatusConnector
        )
        == STATUS_CONN
    )


def test_lookup_status_prefers_exact_part(station_charger):
    """'status' matches the exact part, not 'status_connector'."""
    assert (
        station_charger._get_ocpp_entity_id(domain="sensor", key=OcppEntityMap.Status)
        == STATUS
    )


def test_lookup_missing_returns_none(station_charger):
    """Unknown keys return None."""
    assert station_charger._get_ocpp_entity_id(domain="number", key="bogus") is None


def test_lookup_suffix_fallback_for_connector_session_limit(
    mock_hass, mock_config_entry, mock_device_entry, states
):
    """A ``connector_N_session_current_limit`` part matches by suffix."""
    entity = _registry_entry(
        entity_id="number.test_charger_connector_1_session_current_limit",
        unique_id="number.ocpp.test_charger.connector_1_session_current_limit",
        domain="number",
    )
    charger = _build(mock_hass, mock_config_entry, mock_device_entry, [entity])
    assert (
        charger._get_ocpp_entity_id(
            domain="number", key=OcppEntityMap.SessionCurrentLimit
        )
        == entity.entity_id
    )


def test_lookup_station_on_parent_device(
    mock_hass, mock_config_entry, mock_device_entry, states
):
    """Multi-connector on ocpp >= 0.12: maximum_current lives on the parent."""
    connector = [
        _registry_entry(
            entity_id="number.test_charger_connector_1_session_current_limit",
            unique_id="number.ocpp.test_charger.conn1.session_current_limit",
            domain="number",
        )
    ]
    parent = [
        _registry_entry(
            entity_id=STATION,
            unique_id="number.ocpp.test_charger.maximum_current",
            domain="number",
        )
    ]
    charger = _build(mock_hass, mock_config_entry, mock_device_entry, connector, parent)
    assert charger._station_entity_id() == STATION
    assert charger.control_lever is ControlLever.SESSION


# ---------------------------------------------------------------------------
# Phase mode (validated no-op)
# ---------------------------------------------------------------------------


def test_set_phase_mode_accepts_valid(station_charger):
    """Valid modes are accepted."""
    station_charger.set_phase_mode(PhaseMode.SINGLE)
    station_charger.set_phase_mode(PhaseMode.MULTI)


def test_set_phase_mode_invalid_raises(station_charger):
    """Invalid modes raise."""
    with pytest.raises(ValueError, match="Invalid mode"):
        station_charger.set_phase_mode("not_a_real_mode")


# ---------------------------------------------------------------------------
# Lever selection
# ---------------------------------------------------------------------------


def test_lever_station_without_session_entity(station_charger):
    """ocpp < 0.12: station lever."""
    assert station_charger.control_lever is ControlLever.STATION


def test_lever_session_with_session_entity(session_charger):
    """ocpp >= 0.12: session lever."""
    assert session_charger.control_lever is ControlLever.SESSION


# ---------------------------------------------------------------------------
# Station lever (ocpp < 0.12, or fallback)
# ---------------------------------------------------------------------------


async def test_station_sets_lowest_phase(station_charger, mock_hass):
    """The lowest requested phase is pushed to maximum_current."""
    await station_charger.set_current_limit({Phase.L1: 16, Phase.L2: 10, Phase.L3: 14})
    assert _number_calls(mock_hass) == [(STATION, 10)]


async def test_station_clamps_to_hw_max(station_charger, mock_hass):
    """Values above the hardware maximum are clamped."""
    await station_charger.set_current_limit(_limit(50))
    assert _number_calls(mock_hass) == [(STATION, OCPP_HW_MAX_CURRENT)]


async def test_station_unavailable_aborts(station_charger, mock_hass, states):
    """An unavailable entity (no SmartCharging / offline) is not written."""
    states[STATION] = "unavailable"
    await station_charger.set_current_limit(_limit(12))
    mock_hass.services.async_call.assert_not_called()


async def test_station_unknown_is_written(station_charger, mock_hass, states):
    """ocpp 0.12 shows 'unknown' until a value is confirmed; still writable."""
    states[STATION] = "unknown"
    await station_charger.set_current_limit(_limit(12))
    assert _number_calls(mock_hass) == [(STATION, 12)]


async def test_station_rejection_is_handled(station_charger, mock_hass, states):
    """ocpp 0.12 raises on a rejected profile; no kick follows a rejection."""
    states[STATUS_CONN] = OcppStatusMap.SuspendedEVSE
    mock_hass.services.async_call.side_effect = HomeAssistantError("Rejected")
    await station_charger.set_current_limit(_limit(10))
    assert _switch_calls(mock_hass) == []


async def test_station_snaps_below_min_to_zero(station_charger, mock_hass):
    """Sub-6A requests pause via 0A and remember the pre-snap value."""
    await station_charger.set_current_limit(_limit(4))
    assert _number_calls(mock_hass) == [(STATION, 0)]
    assert station_charger._last_requested == _limit(4)
    assert station_charger._paused_by_us is True


async def test_station_resume_kicks_immediately(station_charger, mock_hass, states):
    """Station lever: profile first, then off->on restart."""
    states[STATUS_CONN] = OcppStatusMap.SuspendedEVSE
    states[STATION] = "0"
    await station_charger.set_current_limit(_limit(10))
    assert _number_calls(mock_hass) == [(STATION, 10)]
    assert _switch_calls(mock_hass) == ["turn_off", "turn_on"]


async def test_station_no_kick_while_charging(station_charger, mock_hass):
    """No restart when already charging."""
    await station_charger.set_current_limit(_limit(10))
    assert _switch_calls(mock_hass) == []


# ---------------------------------------------------------------------------
# Session lever (ocpp >= 0.12)
# ---------------------------------------------------------------------------


async def test_session_writes_only_session_limit(session_charger, mock_hass):
    """The station ceiling is left alone."""
    await session_charger.set_current_limit(_limit(10))
    assert _number_calls(mock_hass) == [(SESSION, 10)]


async def test_session_pause_via_session_limit(session_charger, mock_hass):
    """Pause is a 0A TxProfile, transaction kept alive."""
    await session_charger.set_current_limit(_limit(3))
    assert _number_calls(mock_hass) == [(SESSION, 0)]
    assert _switch_calls(mock_hass) == []


async def test_session_deferred_without_transaction(session_charger, mock_hass, states):
    """Preparing: nothing to bind to yet, nothing drawn; defer."""
    states[SESSION] = "unavailable"
    states[STATUS_CONN] = OcppStatusMap.Preparing
    await session_charger.set_current_limit(_limit(10))
    mock_hass.services.async_call.assert_not_called()
    assert session_charger._task_pending()


async def test_session_bound_when_transaction_starts(
    session_charger, mock_hass, states, fast
):
    """The deferred limit is bound as soon as the slider becomes available."""
    states[SESSION] = "unavailable"
    states[STATUS_CONN] = OcppStatusMap.Preparing
    await session_charger.set_current_limit(_limit(10))
    states[SESSION] = "unknown"  # transaction started
    await run_scheduled(session_charger)
    assert _number_calls(mock_hass) == [(SESSION, 10)]


async def test_session_unbound_while_charging_uses_station_then_restores(
    session_charger, mock_hass, states, fast
):
    """Drawing current with no bound session: station now, session later."""
    states[SESSION] = "unavailable"
    await session_charger.set_current_limit(_limit(8))
    assert _number_calls(mock_hass) == [(STATION, 8)]
    assert session_charger._station_overridden is True

    states[SESSION] = "unknown"
    await run_scheduled(session_charger)
    assert _number_calls(mock_hass) == [(STATION, 8), (SESSION, 8), (STATION, 16)]
    assert session_charger._station_overridden is False


async def test_session_rejection_falls_back_to_station(session_charger, mock_hass):
    """A rejected session write is enforced through the station ceiling."""

    async def _reject_session(**kwargs):
        if kwargs["service_data"]["entity_id"] == SESSION:
            raise HomeAssistantError("Rejected")

    mock_hass.services.async_call.side_effect = _reject_session
    await session_charger.set_current_limit(_limit(9))
    assert _number_calls(mock_hass) == [(SESSION, 9), (STATION, 9)]
    assert session_charger.control_lever is ControlLever.SESSION


async def test_session_disabled_after_repeated_rejections(session_charger, mock_hass):
    """Three rejections in a row switch the charger to the station lever."""

    async def _reject_session(**kwargs):
        if kwargs["service_data"]["entity_id"] == SESSION:
            raise HomeAssistantError("NotSupported")

    mock_hass.services.async_call.side_effect = _reject_session
    for value in (9, 10, 11):
        await session_charger.set_current_limit(_limit(value))
    assert session_charger.control_lever is ControlLever.STATION


async def test_session_resume_does_not_kick_immediately(
    session_charger, mock_hass, states
):
    """Session lever: raise within the transaction, verify later."""
    states[STATUS_CONN] = OcppStatusMap.SuspendedEVSE
    states[SESSION] = "0"
    await session_charger.set_current_limit(_limit(10))
    assert _number_calls(mock_hass) == [(SESSION, 10)]
    assert _switch_calls(mock_hass) == []
    assert session_charger._task_pending()


async def test_session_resume_without_restart(session_charger, mock_hass, states, fast):
    """If the charger resumes on the TxProfile alone, nothing else happens."""
    states[STATUS_CONN] = OcppStatusMap.SuspendedEVSE
    states[SESSION] = "0"
    await session_charger.set_current_limit(_limit(10))
    states[STATUS_CONN] = OcppStatusMap.Charging
    await run_scheduled(session_charger)
    assert _switch_calls(mock_hass) == []


async def test_session_resume_restarts_and_rebinds(
    session_charger, mock_hass, states, fast
):
    """Still suspended after the grace: restart, wait for new tx, rebind."""
    states[STATUS_CONN] = OcppStatusMap.SuspendedEVSE
    states[SESSION] = "0"
    await session_charger.set_current_limit(_limit(10))

    async def _calls(**kwargs):
        if kwargs["domain"] == "switch" and kwargs["service"] == "turn_on":
            states[TX] = "1002"
            states[STATUS_CONN] = OcppStatusMap.Charging
            states[SESSION] = "unknown"

    mock_hass.services.async_call.side_effect = _calls
    await run_scheduled(session_charger)
    assert _switch_calls(mock_hass) == ["turn_off", "turn_on"]
    assert _number_calls(mock_hass) == [(SESSION, 10), (SESSION, 10)]


# ---------------------------------------------------------------------------
# get_current_limit
# ---------------------------------------------------------------------------


def test_get_current_limit_station(station_charger, states):
    """Station lever reports maximum_current."""
    states[STATION] = "14"
    assert station_charger.get_current_limit() == _limit(14)


def test_get_current_limit_is_min_of_station_and_session(session_charger, states):
    """The charger applies min(station, session)."""
    states[SESSION] = "9"
    assert session_charger.get_current_limit() == _limit(9)
    states[STATION] = "7"
    assert session_charger.get_current_limit() == _limit(7)


def test_get_current_limit_unbound_session_reports_station(session_charger, states):
    """New transaction, nothing bound: the station ceiling applies."""
    states[SESSION] = "unknown"
    assert session_charger.get_current_limit() == _limit(16)


async def test_get_current_limit_paused_reports_last_requested(station_charger, states):
    """While we hold the pause, the pre-snap value is reported."""
    await station_charger.set_current_limit(_limit(4))
    states[STATION] = "0"
    states[STATUS_CONN] = OcppStatusMap.SuspendedEVSE
    assert station_charger.get_current_limit() == _limit(4)


async def test_get_current_limit_paused_session_reports_last_requested(
    session_charger, states
):
    """Same for a 0A session limit."""
    await session_charger.set_current_limit(_limit(2))
    states[SESSION] = "0"
    assert session_charger.get_current_limit() == _limit(2)


async def test_get_current_limit_user_raise_during_pause_is_visible(
    station_charger, states
):
    """A user lifting the slider during our pause is not masked."""
    await station_charger.set_current_limit(_limit(4))
    states[STATION] = "12"
    assert station_charger.get_current_limit() == _limit(12)


async def test_get_current_limit_while_binding_reports_last_requested(
    session_charger, states
):
    """While a session limit is pending, the requested value is reported."""
    states[SESSION] = "unavailable"
    states[STATUS_CONN] = OcppStatusMap.Preparing
    await session_charger.set_current_limit(_limit(10))
    assert session_charger.get_current_limit() == _limit(10)


def test_get_current_limit_none_without_entities(
    mock_hass, mock_config_entry, mock_device_entry, states
):
    """No number entities: None."""
    charger = _wire_states(
        _build(mock_hass, mock_config_entry, mock_device_entry, []), states
    )
    assert charger.get_current_limit() is None


# ---------------------------------------------------------------------------
# get_max_current_limit / misc
# ---------------------------------------------------------------------------


def test_get_max_current_limit_from_attribute(station_charger):
    """Max is read from the number entity's ``max`` attribute."""
    station_charger._get_entity_state_attrs.return_value = {"max": 32.0}
    assert station_charger.get_max_current_limit() == _limit(32)


def test_get_max_current_limit_fallback(station_charger):
    """Missing attribute falls back to the hardware default."""
    station_charger._get_entity_state_attrs.return_value = {}
    assert station_charger.get_max_current_limit() == _limit(OCPP_HW_MAX_CURRENT)


def test_has_synced_phase_limits(station_charger):
    """OCPP applies one limit to all phases."""
    assert station_charger.has_synced_phase_limits() is True


@pytest.mark.parametrize(
    ("status", "connected", "can_charge", "charging"),
    [
        (OcppStatusMap.Available, False, False, False),
        (OcppStatusMap.Preparing, True, True, False),
        (OcppStatusMap.Charging, True, True, True),
        (OcppStatusMap.SuspendedEVSE, True, True, False),
        (OcppStatusMap.SuspendedEV, True, True, False),
        (OcppStatusMap.Finishing, True, False, False),
        (OcppStatusMap.Faulted, False, False, False),
    ],
)
def test_status_predicates(
    station_charger, states, status, connected, can_charge, charging
):
    """car_connected / can_charge / is_charging follow the connector status."""
    states[STATUS_CONN] = status
    assert station_charger.car_connected() is connected
    assert station_charger.can_charge() is can_charge
    assert station_charger.is_charging() is charging


async def test_async_setup_noop(station_charger):
    """async_setup is a no-op."""
    await station_charger.async_setup()


async def test_async_unload_cancels_pending(session_charger, states):
    """Unloading cancels a pending session bind."""
    states[SESSION] = "unavailable"
    states[STATUS_CONN] = OcppStatusMap.Preparing
    await session_charger.set_current_limit(_limit(10))
    task = session_charger._task
    await session_charger.async_unload()
    assert task.done()
    assert session_charger._task is None


def test_current_change_settle_time(station_charger):
    """Settle time is 30s for OCPP."""
    assert station_charger.current_change_settle_time == 30


def test_module_exports_lever_enum():
    """Lever names match the OCPP entity keys."""
    assert ControlLever.SESSION == ocpp_mod.OcppEntityMap.SessionCurrentLimit
    assert ControlLever.STATION == ocpp_mod.OcppEntityMap.MaximumCurrent
