"""Tests for sensor startup grace period and unavailability handling."""

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from freezegun import freeze_time
from homeassistant.core import HomeAssistant
from homeassistant.helpers.issue_registry import async_get as async_get_issue_registry

from custom_components.evse_load_balancer.const import (
    COORDINATOR_STATE_INITIALIZING,
    COORDINATOR_STATE_MONITORING_LOAD,
    DOMAIN,
    REPAIR_ISSUE_SENSORS_UNAVAILABLE,
    SENSOR_STARTUP_GRACE_PERIOD,
)
from custom_components.evse_load_balancer.coordinator import (
    EVSELoadBalancerCoordinator,
)
from custom_components.evse_load_balancer.meters.custom_meter import CustomMeter
from custom_components.evse_load_balancer.meters.meter import Phase

from .helpers.mock_charger import MockCharger


@pytest.fixture
def mock_custom_meter_unavailable(hass: HomeAssistant):
    """Create a mock custom meter with unavailable sensors."""
    meter = MagicMock(spec=CustomMeter)
    meter.hass = hass
    meter.get_active_phase_current = MagicMock(return_value=None)
    meter.get_unavailable_sensors = MagicMock(
        return_value=["sensor.consumption_l1", "sensor.voltage_l1"]
    )
    meter.get_tracking_entities = MagicMock(return_value=[])
    return meter


@pytest.fixture
def mock_custom_meter_available(hass: HomeAssistant):
    """Create a mock custom meter with available sensors."""
    meter = MagicMock(spec=CustomMeter)
    meter.hass = hass
    meter.get_active_phase_current = MagicMock(return_value=10)
    meter.get_unavailable_sensors = MagicMock(return_value=[])
    meter.get_tracking_entities = MagicMock(return_value=[])
    return meter


@pytest.fixture
def mock_config_entry():
    """Create a mock config entry."""
    entry = MagicMock()
    entry.entry_id = "test_entry"
    entry.data = {
        "fuse_size": 25,
        "phase_count": 3,
    }
    entry.options = {}
    entry.add_update_listener = MagicMock(return_value=MagicMock())
    return entry


@pytest.mark.asyncio
async def test_coordinator_starts_in_grace_period(
    hass: HomeAssistant,
    mock_config_entry,
    mock_custom_meter_unavailable,
):
    """Test that coordinator starts in grace period state."""
    charger = MockCharger(hass, "test_charger_1", 1, 32)
    charger.async_setup = AsyncMock()

    coordinator = EVSELoadBalancerCoordinator(
        hass=hass,
        config_entry=mock_config_entry,
        meter=mock_custom_meter_unavailable,
        charger=charger,
    )

    # Should be in grace period immediately after creation
    assert coordinator._is_in_startup_grace_period() is True
    assert coordinator.get_load_balancing_state == COORDINATOR_STATE_INITIALIZING


@pytest.mark.asyncio
async def test_grace_period_expires_after_timeout(
    hass: HomeAssistant,
    mock_config_entry,
    mock_custom_meter_unavailable,
):
    """Test that grace period expires after SENSOR_STARTUP_GRACE_PERIOD seconds."""
    charger = MockCharger(hass, "test_charger_1", 1, 32)
    charger.async_setup = AsyncMock()

    with freeze_time("2025-01-01 12:00:00") as frozen_time:
        coordinator = EVSELoadBalancerCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            meter=mock_custom_meter_unavailable,
            charger=charger,
        )

        # Initially in grace period
        assert coordinator._is_in_startup_grace_period() is True

        # Move time forward but still within grace period
        frozen_time.tick(delta=timedelta(seconds=SENSOR_STARTUP_GRACE_PERIOD - 1))
        assert coordinator._is_in_startup_grace_period() is True

        # Move past grace period
        frozen_time.tick(delta=timedelta(seconds=2))
        assert coordinator._is_in_startup_grace_period() is False


@pytest.mark.asyncio
async def test_no_repair_issue_during_grace_period(
    hass: HomeAssistant,
    mock_config_entry,
    mock_custom_meter_unavailable,
):
    """Test that no repair issue is created during grace period."""
    charger = MockCharger(hass, "test_charger_1", 1, 32)
    charger.async_setup = AsyncMock()
    charger.async_unload = AsyncMock()
    charger.can_charge = MagicMock(return_value=True)
    charger.get_current_limit = MagicMock(return_value={Phase.L1: 16})

    coordinator = EVSELoadBalancerCoordinator(
        hass=hass,
        config_entry=mock_config_entry,
        meter=mock_custom_meter_unavailable,
        charger=charger,
    )

    await coordinator.async_setup()

    # Trigger update cycle during grace period
    coordinator._execute_update_cycle(datetime.now().astimezone())

    # Should not create repair issue
    issue_registry = async_get_issue_registry(hass)
    issue = issue_registry.async_get_issue(DOMAIN, REPAIR_ISSUE_SENSORS_UNAVAILABLE)
    assert issue is None

    # Cleanup
    await coordinator.async_unload()


@pytest.mark.asyncio
async def test_repair_issue_created_after_grace_period(
    hass: HomeAssistant,
    mock_config_entry,
    mock_custom_meter_unavailable,
):
    """Test that repair issue is created after grace period expires."""
    charger = MockCharger(hass, "test_charger_1", 1, 32)
    charger.async_setup = AsyncMock()
    charger.async_unload = AsyncMock()
    charger.can_charge = MagicMock(return_value=True)
    charger.get_current_limit = MagicMock(return_value={Phase.L1: 16})

    with freeze_time("2025-01-01 12:00:00") as frozen_time:
        coordinator = EVSELoadBalancerCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            meter=mock_custom_meter_unavailable,
            charger=charger,
        )

        await coordinator.async_setup()

        # Move past grace period
        frozen_time.tick(delta=timedelta(seconds=SENSOR_STARTUP_GRACE_PERIOD + 1))

        # Trigger update cycle after grace period
        coordinator._execute_update_cycle(datetime.now().astimezone())

        # Should create repair issue
        issue_registry = async_get_issue_registry(hass)
        issue = issue_registry.async_get_issue(DOMAIN, REPAIR_ISSUE_SENSORS_UNAVAILABLE)
        assert issue is not None
        assert issue.translation_key == "sensors_unavailable"

        # Cleanup
        await coordinator.async_unload()


@pytest.mark.asyncio
async def test_custom_meter_tracks_unavailable_sensors(hass: HomeAssistant):
    """Test that CustomMeter properly tracks unavailable sensors."""
    mock_entry = MagicMock()
    mock_entry.data = {
        "l1": {
            "consumption": "sensor.consumption_l1",
            "production": "sensor.production_l1",
            "voltage": "sensor.voltage_l1",
        }
    }

    # Mock unavailable state
    hass.states.async_set("sensor.consumption_l1", "unavailable")

    meter = CustomMeter(hass, mock_entry)

    # Should return None and track the sensor
    result = meter._get_state("sensor.consumption_l1")
    assert result is None
    assert "sensor.consumption_l1" in meter.get_unavailable_sensors()


@pytest.mark.asyncio
async def test_custom_meter_removes_sensors_when_available(hass: HomeAssistant):
    """Test that CustomMeter removes sensors from unavailable list when they recover."""
    mock_entry = MagicMock()
    mock_entry.data = {
        "l1": {
            "consumption": "sensor.consumption_l1",
            "production": "sensor.production_l1",
            "voltage": "sensor.voltage_l1",
        }
    }

    # Start with unavailable state
    hass.states.async_set("sensor.consumption_l1", "unavailable")

    meter = CustomMeter(hass, mock_entry)

    # Get state while unavailable
    meter._get_state("sensor.consumption_l1")
    assert "sensor.consumption_l1" in meter.get_unavailable_sensors()

    # Update to available state
    hass.states.async_set("sensor.consumption_l1", "100.5")

    # Get state again
    result = meter._get_state("sensor.consumption_l1")
    assert result == 100.5
    assert "sensor.consumption_l1" not in meter.get_unavailable_sensors()


@pytest.mark.asyncio
async def test_custom_meter_handles_unknown_state(hass: HomeAssistant):
    """Test that CustomMeter handles 'unknown' state like 'unavailable'."""
    mock_entry = MagicMock()
    mock_entry.data = {}

    hass.states.async_set("sensor.test", "unknown")

    meter = CustomMeter(hass, mock_entry)

    result = meter._get_state("sensor.test")
    assert result is None
    assert "sensor.test" in meter.get_unavailable_sensors()


@pytest.mark.asyncio
async def test_custom_meter_handles_parse_errors(hass: HomeAssistant):
    """Test that CustomMeter tracks sensors that fail to parse."""
    mock_entry = MagicMock()
    mock_entry.data = {}

    hass.states.async_set("sensor.test", "not_a_number")

    meter = CustomMeter(hass, mock_entry)

    result = meter._get_state("sensor.test")
    assert result is None
    assert "sensor.test" in meter.get_unavailable_sensors()


@pytest.mark.asyncio
async def test_coordinator_state_changes_after_grace_period(
    hass: HomeAssistant,
    mock_config_entry,
    mock_custom_meter_unavailable,
):
    """Test that coordinator state changes from initializing after grace period."""
    charger = MockCharger(hass, "test_charger_1", 1, 32)
    charger.async_setup = AsyncMock()
    charger.async_unload = AsyncMock()
    charger.can_charge = MagicMock(return_value=False)

    with freeze_time("2025-01-01 12:00:00") as frozen_time:
        coordinator = EVSELoadBalancerCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            meter=mock_custom_meter_unavailable,
            charger=charger,
        )

        await coordinator.async_setup()

        # Should be initializing during grace period
        assert coordinator.get_load_balancing_state == COORDINATOR_STATE_INITIALIZING

        # Move past grace period
        frozen_time.tick(delta=timedelta(seconds=SENSOR_STARTUP_GRACE_PERIOD + 1))

        # Should no longer be initializing (even with unavailable sensors)
        # State should be based on charger state
        assert coordinator.get_load_balancing_state != COORDINATOR_STATE_INITIALIZING

        # Cleanup
        await coordinator.async_unload()


@pytest.mark.asyncio
async def test_repair_issue_dismissed_on_unload(
    hass: HomeAssistant,
    mock_config_entry,
    mock_custom_meter_unavailable,
):
    """Test that repair issue is dismissed when coordinator is unloaded."""
    charger = MockCharger(hass, "test_charger_1", 1, 32)
    charger.async_setup = AsyncMock()
    charger.async_unload = AsyncMock()
    charger.can_charge = MagicMock(return_value=True)
    charger.get_current_limit = MagicMock(return_value={Phase.L1: 16})

    with freeze_time("2025-01-01 12:00:00") as frozen_time:
        coordinator = EVSELoadBalancerCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            meter=mock_custom_meter_unavailable,
            charger=charger,
        )

        await coordinator.async_setup()

        # Create repair issue
        frozen_time.tick(delta=timedelta(seconds=SENSOR_STARTUP_GRACE_PERIOD + 1))
        coordinator._execute_update_cycle(datetime.now().astimezone())

        issue_registry = async_get_issue_registry(hass)
        issue = issue_registry.async_get_issue(DOMAIN, REPAIR_ISSUE_SENSORS_UNAVAILABLE)
        assert issue is not None

        # Unload coordinator
        await coordinator.async_unload()

        # Issue should be dismissed
        issue = issue_registry.async_get_issue(DOMAIN, REPAIR_ISSUE_SENSORS_UNAVAILABLE)
        assert issue is None


@pytest.mark.asyncio
async def test_repair_issue_only_created_once(
    hass: HomeAssistant,
    mock_config_entry,
    mock_custom_meter_unavailable,
):
    """Test that repair issue is only created once even with multiple update cycles."""
    charger = MockCharger(hass, "test_charger_1", 1, 32)
    charger.async_setup = AsyncMock()
    charger.async_unload = AsyncMock()
    charger.can_charge = MagicMock(return_value=True)
    charger.get_current_limit = MagicMock(return_value={Phase.L1: 16})

    with freeze_time("2025-01-01 12:00:00") as frozen_time:
        coordinator = EVSELoadBalancerCoordinator(
            hass=hass,
            config_entry=mock_config_entry,
            meter=mock_custom_meter_unavailable,
            charger=charger,
        )

        await coordinator.async_setup()

        # Move past grace period
        frozen_time.tick(delta=timedelta(seconds=SENSOR_STARTUP_GRACE_PERIOD + 1))

        # Trigger multiple update cycles
        with patch(
            "custom_components.evse_load_balancer.coordinator.async_create_issue"
        ) as mock_create_issue:
            coordinator._execute_update_cycle(datetime.now().astimezone())
            coordinator._execute_update_cycle(datetime.now().astimezone())
            coordinator._execute_update_cycle(datetime.now().astimezone())

            # Should only be called once
            assert mock_create_issue.call_count == 1

        # Cleanup
        await coordinator.async_unload()
