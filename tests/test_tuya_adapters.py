"""Integration tests for the actual Tuya Local entity profiles and allocator."""

import asyncio
from datetime import timedelta
from unittest.mock import Mock, patch

import pytest
from homeassistant.exceptions import ServiceNotFound
from homeassistant.helpers import device_registry as dr, entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.evse_load_balancer.chargers import charger_factory
from custom_components.evse_load_balancer.chargers.feyree_charger import FeyreeCharger
from custom_components.evse_load_balancer.config_flow import EvseLoadBalancerConfigFlow
from custom_components.evse_load_balancer.const import DOMAIN, Phase
from custom_components.evse_load_balancer.coordinator import EVSELoadBalancerCoordinator
from custom_components.evse_load_balancer.meters import meter_factory
from custom_components.evse_load_balancer.power_allocator import PowerAllocator


@pytest.fixture
async def tuya(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "fuse_size": 16,
            "phase_count": 3,
            "charger_max_current": 16,
        },
        options={"allow_temporary_overcurrent": False, "charge_limit_hysteresis": 1},
    )
    entry.add_to_hass(hass)
    registry = dr.async_get(hass)
    devices = {}
    ids = {}
    for uid, manufacturer, model in [
        ("charger", "Feyree", "22kW 3phase"),
        ("meter", "VERATTI", "V4 3-phase circuit breaker"),
    ]:
        devices[uid] = registry.async_get_or_create(
            config_entry_id=entry.entry_id,
            identifiers={("tuya_local", uid)},
            manufacturer=manufacturer,
            model=model,
            name=uid,
        )
    entities = er.async_get(hass)
    profiles = [
        (
            "charger",
            "number_set_charge_current",
            "renamed_limit",
            "10",
            {"min": 6, "max": 32, "unit_of_measurement": "A"},
        ),
        (
            "charger",
            "select_charging",
            "renamed_mode",
            "on_demand",
            {"options": ["on", "off", "on_demand"]},
        ),
        ("charger", "sensor_status", "renamed_status", "charging", {}),
    ] + [
        (
            "meter",
            f"sensor_current_{p}",
            f"renamed_phase_{p}",
            "1.2",
            {"unit_of_measurement": "A"},
        )
        for p in "abc"
    ]
    for uid, config_id, entity_name, state, attrs in profiles:
        domain = config_id.split("_")[0]
        entity = entities.async_get_or_create(
            domain,
            "tuya_local",
            f"{uid}-{config_id}",
            device_id=devices[uid].id,
            suggested_object_id=entity_name,
        )
        ids[config_id] = entity.entity_id
        hass.states.async_set(entity.entity_id, state, attrs)
    calls = []

    async def control(call):
        calls.append((call.domain, call.service, dict(call.data)))
        entity_id = call.data["entity_id"]
        old = hass.states.get(entity_id)
        hass.states.async_set(
            entity_id,
            str(call.data.get("value", call.data.get("option"))),
            old.attributes,
        )

    hass.services.async_register("number", "set_value", control)
    hass.services.async_register("select", "select_option", control)
    charger = await charger_factory(hass, entry, devices["charger"].id)
    meter = await meter_factory(hass, entry, False, devices["meter"].id)
    await charger.async_setup()
    return entry, devices, ids, calls, charger, meter


def limits(value):
    return dict.fromkeys(Phase, value)


async def test_factories_and_renamed_entities(tuya):
    entry, devices, ids, calls, charger, meter = tuya
    assert isinstance(charger, FeyreeCharger)
    assert meter.get_tracking_entities() == [ids[f"sensor_current_{p}"] for p in "abc"]
    assert charger.get_max_current_limit() == limits(16)
    assert calls == []  # Setup never starts or changes charging.
    for model in ["unknown", "11kW wallbox"]:
        assert not FeyreeCharger.is_charger_device(
            Mock(identifiers={("tuya_local", "x")}, manufacturer="Feyree", model=model)
        )


@pytest.mark.parametrize(
    "value,unit,expected",
    [
        ("2.58", "A", 3),
        ("0", "A", 0),
        ("970", "mA", 1),
        ("unavailable", "A", None),
        ("unknown", "A", None),
        ("NaN", "A", None),
        ("inf", "A", None),
        ("-1", "A", None),
        ("500", "W", None),
    ],
)
async def test_meter_units_invalid_and_rounding(hass, tuya, value, unit, expected):
    _, _, ids, _, _, meter = tuya
    hass.states.async_set(ids["sensor_current_a"], value, {"unit_of_measurement": unit})
    assert meter.get_active_phase_current(Phase.L1) == expected


async def test_meter_unchanged_reading_while_online(tuya, freezer):
    *_, meter = tuya
    assert meter.get_active_phase_current(Phase.L1) == 2
    freezer.tick(timedelta(minutes=10))
    assert meter.get_active_phase_current(Phase.L1) == 2


async def test_meter_offline_readings_are_rejected(hass, tuya, freezer):
    _, _, ids, _, _, meter = tuya
    freezer.tick(timedelta(minutes=10))
    for p, phase in zip("abc", Phase):
        hass.states.async_set(
            ids[f"sensor_current_{p}"], "unavailable", {"unit_of_measurement": "A"}
        )
        assert meter.get_active_phase_current(phase) is None


@pytest.mark.parametrize("action", ["disable", "remove"])
async def test_meter_sensor_disabled_or_removed_after_setup(hass, tuya, action):
    _, _, ids, _, _, meter = tuya
    registry = er.async_get(hass)
    entity_id = ids["sensor_current_a"]
    if action == "disable":
        registry.async_update_entity(
            entity_id, disabled_by=er.RegistryEntryDisabler.USER
        )
    else:
        registry.async_remove(entity_id)
    assert meter.get_active_phase_current(Phase.L1) is None


async def test_common_minimum_and_circuit_cap(tuya):
    _, _, ids, calls, charger, _ = tuya
    await charger.set_current_limit({Phase.L1: 16, Phase.L2: 8, Phase.L3: 12})
    assert calls[-1] == (
        "number",
        "set_value",
        {"entity_id": ids["number_set_charge_current"], "value": 8},
    )
    await charger.set_current_limit(limits(32))
    assert calls[-1][2]["value"] == 16


@pytest.mark.parametrize("mode", ["on", "on_demand"])
async def test_pause_and_ordered_resume(hass, tuya, mode):
    _, _, ids, calls, charger, _ = tuya
    hass.states.async_set(ids["select_charging"], mode)
    await charger.set_current_limit(limits(5))
    assert calls == [
        (
            "select",
            "select_option",
            {"entity_id": ids["select_charging"], "option": "off"},
        )
    ]
    assert charger.can_charge()
    assert charger.get_current_limit() == limits(0)
    await charger.set_current_limit(limits(8))
    assert calls[-2:] == [
        (
            "number",
            "set_value",
            {"entity_id": ids["number_set_charge_current"], "value": 8},
        ),
        (
            "select",
            "select_option",
            {"entity_id": ids["select_charging"], "option": "on"},
        ),
    ]


async def test_balancer_pause_reported_as_charged_recovers(hass, tuya):
    _, _, ids, calls, charger, _ = tuya
    await charger.async_handle_meter_unavailable()
    hass.states.async_set(ids["sensor_status"], "charged")
    assert charger.can_charge()
    await charger.set_current_limit(limits(6))
    assert calls[-2:] == [
        (
            "number",
            "set_value",
            {"entity_id": ids["number_set_charge_current"], "value": 6},
        ),
        (
            "select",
            "select_option",
            {"entity_id": ids["select_charging"], "option": "on"},
        ),
    ]
    assert not charger.can_charge()  # A genuinely completed session stays stopped.


@pytest.mark.parametrize("mode", ["off", "on", "on_demand"])
async def test_completed_session_without_owned_pause_is_never_started(hass, tuya, mode):
    _, _, ids, calls, charger, _ = tuya
    hass.states.async_set(ids["sensor_status"], "charged")
    hass.states.async_set(ids["select_charging"], mode)
    await charger.async_handle_meter_unavailable()
    await charger.set_current_limit(limits(6))
    assert not charger.can_charge()
    assert calls == []


async def test_new_feyree_session_preserves_selected_six_amps(hass, tuya):
    _, _, ids, _, charger, _ = tuya
    attrs = hass.states.get(ids["number_set_charge_current"]).attributes
    hass.states.async_set(ids["number_set_charge_current"], "6", attrs)
    hass.states.async_set(ids["select_charging"], "off")
    hass.states.async_set(ids["sensor_status"], "charged")
    allocator = PowerAllocator()
    allocator.add_charger_and_initialize(charger)
    hass.states.async_set(ids["select_charging"], "on_demand")
    hass.states.async_set(ids["sensor_status"], "charging")
    allocator.update_allocation(limits(9))
    assert allocator._chargers[charger.id].requested_current == limits(6)


async def test_manual_off_and_fault_are_never_started(hass, tuya):
    _, _, ids, calls, charger, _ = tuya
    hass.states.async_set(ids["select_charging"], "off")
    await charger.set_current_limit(limits(10))
    assert calls == []
    assert not charger.can_charge()
    hass.states.async_set(ids["select_charging"], "on")
    hass.states.async_set(ids["sensor_status"], "fault")
    await charger.set_current_limit(limits(10))
    assert calls == []


async def test_reload_does_not_resume_previous_pause(hass, tuya):
    entry, devices, ids, calls, charger, _ = tuya
    await charger.set_current_limit(limits(0))
    fresh = FeyreeCharger(hass, entry, devices["charger"])
    await fresh.async_setup()
    await fresh.set_current_limit(limits(10))
    assert len(calls) == 1
    assert not fresh.can_charge()


async def test_resume_number_failure_keeps_charger_off(hass, tuya):
    *_, charger, meter = tuya
    await charger.set_current_limit(limits(0))
    hass.services.async_remove("number", "set_value")
    with pytest.raises(ServiceNotFound):
        await charger.set_current_limit(limits(8))
    assert charger.get_current_limit() == limits(0)


async def test_allocator_pause_recovery_does_not_add_phantom_current(tuya):
    *_, charger, meter = tuya
    allocator = PowerAllocator()
    allocator.add_charger_and_initialize(charger)
    # Charging at 10 A, whole-home phase load 21 A: reduce 5 A to a pause.
    reduced = allocator.update_allocation({Phase.L1: -5, Phase.L2: 4, Phase.L3: 4})
    assert reduced[charger.id] == limits(0)
    await charger.set_current_limit(reduced[charger.id])
    allocator.update_applied_current(charger.id, reduced[charger.id], 0)
    assert allocator._chargers[charger.id].requested_current == limits(10)
    # Home now uses 11 A with EV paused: 5 A spare must NOT resume at 6 or 10 A.
    assert allocator.update_allocation(limits(5)) == {}
    recovered = allocator.update_allocation(limits(6))
    assert recovered[charger.id] == limits(6)
    await charger.set_current_limit(recovered[charger.id])
    assert charger.get_current_limit() == limits(6)


async def test_manual_setting_above_cap_is_reduced_with_zero_availability(hass, tuya):
    _, _, ids, _, charger, _ = tuya
    hass.states.async_set(ids["number_set_charge_current"], "32", {"min": 6, "max": 32})
    allocator = PowerAllocator()
    allocator.add_charger_and_initialize(charger)
    assert allocator.update_allocation(limits(0))[charger.id] == limits(16)


async def test_coordinator_outage_preserves_recovery_target(hass, tuya):
    entry, devices, ids, calls, charger, meter = tuya
    coordinator = EVSELoadBalancerCoordinator(hass, entry, meter, charger)
    await coordinator.async_setup()
    hass.states.async_set(
        ids["sensor_current_a"], "unavailable", {"unit_of_measurement": "A"}
    )
    coordinator._execute_update_cycle(dt_util.utcnow())
    await hass.async_block_till_done()
    assert charger.get_current_limit() == limits(0)
    assert coordinator._power_allocator._chargers[
        charger.id
    ].requested_current == limits(10)
    hass.states.async_set(ids["sensor_current_a"], "11", {"unit_of_measurement": "A"})
    coordinator._power_allocator._chargers[charger.id].last_update_time = 0
    assert coordinator._power_allocator.update_allocation(limits(5)) == {}
    assert coordinator._power_allocator.update_allocation(limits(6))[
        charger.id
    ] == limits(6)
    await coordinator.async_unload()


async def test_coordinator_unload_cancels_pending_pause(hass, tuya):
    entry, _, ids, calls, charger, meter = tuya
    coordinator = EVSELoadBalancerCoordinator(hass, entry, meter, charger)
    await coordinator.async_setup()
    started = asyncio.Event()
    release = asyncio.Event()

    async def delayed_pause(timestamp):
        started.set()
        await release.wait()
        return await charger.async_handle_meter_unavailable()

    with patch.object(
        coordinator,
        "_async_handle_meter_unavailable",
        side_effect=delayed_pause,
    ):
        hass.states.async_set(ids["sensor_current_a"], "unavailable")
        coordinator._execute_update_cycle(dt_util.utcnow())
        task = coordinator._meter_pause_task
        try:
            await asyncio.wait_for(started.wait(), timeout=1)
            assert not task.done()
        finally:
            await coordinator.async_unload()
        assert task.cancelled()
    assert calls == []


async def test_coordinator_failed_pause_does_not_record_applied_zero(
    hass, tuya, caplog
):
    entry, _, ids, calls, charger, meter = tuya
    coordinator = EVSELoadBalancerCoordinator(hass, entry, meter, charger)
    await coordinator.async_setup()
    hass.services.async_remove("select", "select_option")
    hass.states.async_set(ids["sensor_current_a"], "unavailable")
    coordinator._execute_update_cycle(dt_util.utcnow())
    await hass.async_block_till_done()
    assert "Unable to pause charger while meter is unavailable" in caplog.text
    assert charger.get_current_limit() == limits(10)
    state = coordinator._power_allocator._chargers[charger.id]
    assert state.last_applied_current == limits(10)
    assert calls == []
    await coordinator.async_unload()


async def test_feyree_config_flow_requires_explicit_cap(hass, tuya):
    entry, devices, ids, calls, charger, meter = tuya
    flow = EvseLoadBalancerConfigFlow()
    flow.hass = hass
    form = await flow.async_step_user(
        {
            "charger_device": devices["charger"].id,
            "meter_device": devices["meter"].id,
            "fuse_size": 16,
            "phase_count": 3,
        }
    )
    assert form["step_id"] == "feyree"
    invalid = await flow.async_step_feyree({"charger_max_current": 5})
    assert invalid["errors"] == {"charger_max_current": "invalid_charger_max_current"}
    configured = await flow.async_step_feyree({"charger_max_current": 16})
    assert configured["type"] == "create_entry"
    assert configured["data"]["charger_max_current"] == 16
    assert configured["options"]["allow_temporary_overcurrent"] is False
    assert calls == []
