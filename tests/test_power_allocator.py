"""Tests for PowerAllocator class."""

import pytest
from custom_components.evse_load_balancer.power_allocator import ChargerState, PowerAllocator
from custom_components.evse_load_balancer.const import Phase
from .helpers.mock_charger import MockCharger
from datetime import datetime
from time import time


@pytest.fixture
def power_allocator():
    """Fixture for PowerAllocator."""
    return PowerAllocator()


def test_add_charger_successful(power_allocator: PowerAllocator):
    """Test successfully adding a new charger."""
    # Create a real mock charger with initial current of 10A
    mock_charger = MockCharger(initial_current=10, charger_id="charger1")

    power_allocator.add_charger(mock_charger)

    assert "charger1" in power_allocator._chargers
    assert power_allocator._chargers["charger1"].charger == mock_charger
    assert power_allocator._chargers["charger1"].initialized is False
    assert power_allocator._chargers["charger1"].requested_current is None
    assert power_allocator._chargers["charger1"].last_calculated_current is None
    assert power_allocator._chargers["charger1"].last_applied_current is None


def test_initialize(power_allocator: PowerAllocator):
    """Test successfully adding a new charger."""
    # Create a real mock charger with initial current of 10A
    mock_charger = MockCharger(initial_current=10, charger_id="charger1")

    power_allocator.add_charger_and_initialize(mock_charger)

    assert power_allocator._chargers["charger1"].requested_current == {
        Phase.L1: 10, Phase.L2: 10, Phase.L3: 10
    }
    assert power_allocator._chargers["charger1"].last_applied_current == {
        Phase.L1: 10, Phase.L2: 10, Phase.L3: 10
    }


def test_get_current_limit(power_allocator: PowerAllocator):
    """Test get_current_limit method."""
    # Create a real mock charger with initial current of 10A
    mock_charger = MockCharger(initial_current=10, charger_id="charger1")

    power_allocator.add_charger_and_initialize(mock_charger)

    state: ChargerState = power_allocator._chargers["charger1"]
    state.last_applied_current = {Phase.L1: 10, Phase.L2: 10, Phase.L3: 10}
    state.last_update_time = int(time())

    assert state.get_current_limit() == {
        Phase.L1: 10, Phase.L2: 10, Phase.L3: 10
    }

    state.last_applied_current = {Phase.L1: 5, Phase.L2: 5, Phase.L3: 5}
    state.last_update_time = int(time())

    assert state.get_current_limit() == {
        Phase.L1: 5, Phase.L2: 5, Phase.L3: 5
    }

    state.last_update_time = int(time()) - 30  # simulate delay

    assert state.get_current_limit() == {
        Phase.L1: 10, Phase.L2: 10, Phase.L3: 10
    }


def test_add_charger_and_initialize(power_allocator: PowerAllocator):
    """Test adding of charger that immediately initializes."""
    # Create a real mock charger with initial current of 10A
    mock_charger = MockCharger(initial_current=10, charger_id="charger1")

    power_allocator.add_charger_and_initialize(mock_charger)

    assert "charger1" in power_allocator._chargers
    assert power_allocator._chargers["charger1"].charger == mock_charger
    assert power_allocator._chargers["charger1"].initialized is True
    assert power_allocator._chargers["charger1"].requested_current == {
        Phase.L1: 10, Phase.L2: 10, Phase.L3: 10
    }
    assert power_allocator._chargers["charger1"].last_applied_current == {
        Phase.L1: 10, Phase.L2: 10, Phase.L3: 10
    }


def test_add_charger_already_exists(power_allocator: PowerAllocator):
    """Test adding a charger that already exists."""
    # Add the first charger
    first_charger = MockCharger(initial_current=10, charger_id="charger1")
    power_allocator.add_charger(first_charger)

    # Try to add another charger with the same ID
    second_charger = MockCharger(initial_current=16, charger_id="charger1")

    assert power_allocator.add_charger(second_charger) is False
    # The original charger should still be there
    assert power_allocator._chargers["charger1"].charger == first_charger


def test_add_charger_initialization_fails(power_allocator: PowerAllocator):
    """Test adding a charger that fails to initialize."""
    # Create a mock charger that will return None for get_current_limit
    mock_charger = MockCharger(initial_current=10, charger_id="charger1")
    # Make get_current_limit return None to simulate initialization failure
    mock_charger.get_current_limit = lambda: None

    power_allocator.add_charger_and_initialize(mock_charger)

    assert "charger1" in power_allocator._chargers
    assert power_allocator._chargers["charger1"].initialized is False


def test_should_monitor(power_allocator: PowerAllocator):
    """Test should_monitor method."""
    # Add two chargers with different can_charge states
    charger1 = MockCharger()
    charger1.set_can_charge(True)

    charger2 = MockCharger()
    charger2.set_can_charge(False)

    power_allocator.add_charger_and_initialize(charger1)
    power_allocator.add_charger_and_initialize(charger2)

    # With one charger that can charge, should_monitor should return True
    assert power_allocator.should_monitor() is True

    # If no charger can charge, should_monitor should return False
    charger1.set_can_charge(False)
    assert power_allocator.should_monitor() is False


def test_update_allocation_overcurrent(power_allocator: PowerAllocator):
    """Test update_allocation method with overcurrent situation."""
    # Create and add a charger
    charger = MockCharger(initial_current=10, charger_id="charger1")
    charger.set_can_charge(True)
    power_allocator.add_charger_and_initialize(charger)

    # Simulate overcurrent
    available_currents = {
        Phase.L1: -8,
        Phase.L2: -2,
        Phase.L3: 2
    }

    result = power_allocator.update_allocation(available_currents)

    # Verify results
    assert "charger1" in result
    assert result["charger1"] == {
        Phase.L1: 2,
        Phase.L2: 2,
        Phase.L3: 2
    }


def test_update_allocation_recovery(power_allocator: PowerAllocator):
    """Test update_allocation method with recovery situation."""
    # Create and add a charger that's been reduced
    charger = MockCharger(initial_current=16, charger_id="charger1")
    charger.set_can_charge(True)
    # Set current limit lower than the requested limit
    charger.set_current_limits({
        Phase.L1: 7,
        Phase.L2: 8,
        Phase.L3: 10
    })
    power_allocator.add_charger_and_initialize(charger)

    # Make sure the power allocator knows the requested current
    power_allocator._chargers["charger1"].requested_current = {
        Phase.L1: 16,
        Phase.L2: 16,
        Phase.L3: 16
    }

    # Simulate recovery with available capacity
    available_currents = {
        Phase.L1: 5,
        Phase.L2: 5,
        Phase.L3: 5
    }

    result = power_allocator.update_allocation(available_currents)

    # Verify results
    assert "charger1" in result
    assert result["charger1"] == {
        Phase.L1: 12,
        Phase.L2: 12,
        Phase.L3: 12
    }


def test_update_applied_current(power_allocator: PowerAllocator):
    """Test update_applied_current method."""
    # Create a charger
    charger = MockCharger(initial_current=10, charger_id="charger1")
    power_allocator.add_charger_and_initialize(charger)

    timestamp = datetime.now().timestamp()
    # Simulate application of currents
    power_allocator.update_applied_current(
        "charger1",
        dict.fromkeys(Phase, 5),
        timestamp=timestamp
    )

    # Verify the applied current
    state = power_allocator._chargers["charger1"]
    assert state.last_applied_current == {
        Phase.L1: 5,
        Phase.L2: 5,
        Phase.L3: 5
    }
    assert state.last_update_time == timestamp


def test_manual_override_detection(power_allocator: PowerAllocator):
    """Test manual override detection."""
    # Create a charger
    charger = MockCharger(initial_current=10, charger_id="charger1")
    power_allocator.add_charger_and_initialize(charger)

    # Simulate application of currents
    power_allocator.update_applied_current(
        "charger1",
        dict.fromkeys(Phase, 10),
        timestamp=(time() - 30)  # make sure we pass a timestamp
    )

    # Simulate manual override by changing the limits outside the allocator
    charger.set_current_limits({
        Phase.L1: 16,
        Phase.L2: 16,
        Phase.L3: 16
    })

    # Check if the override is detected
    state = power_allocator._chargers["charger1"]
    state.detect_manual_override()

    assert state.manual_override_detected is True
    # The requested current should be updated to the new values
    assert state.requested_current == {
        Phase.L1: 16,
        Phase.L2: 16,
        Phase.L3: 16
    }


def test_manual_override_detection_maintains_charger_reset_at_session_start(power_allocator: PowerAllocator):
    """Test is charger is reset to max charger limits at session start."""
    charger = MockCharger(initial_current=10, charger_id="charger1", max_current=16)
    charger.set_can_charge(False)  # not charging
    power_allocator.add_charger_and_initialize(charger)

    # Simulate application of currents
    state: ChargerState = power_allocator._chargers["charger1"]
    state.detect_manual_override()

    # Detecting manual override after setting charge will take the
    # charger's max current and set it as requested.
    assert state._active_session is False
    assert state.requested_current == dict.fromkeys(Phase, 10)

    charger.set_can_charge(True)  # start charging

    # Simulate new currents being applied to the charger from the outside
    state.detect_manual_override()
    charger.set_current_limits(dict.fromkeys(Phase, 10))

    assert state._active_session is True
    assert state.requested_current == dict.fromkeys(Phase, 16)


def test_multiple_chargers_allocation(power_allocator: PowerAllocator):
    """Test allocating current to multiple chargers."""
    # Create two chargers
    charger1 = MockCharger(initial_current=10, charger_id="charger1")
    charger1.set_can_charge(True)

    charger2 = MockCharger(initial_current=16, charger_id="charger2")
    charger2.set_can_charge(True)

    power_allocator.add_charger(charger1)
    power_allocator.add_charger(charger2)

    # Simulate overcurrent
    available_currents = {
        Phase.L1: -10,
        Phase.L2: -4,
        Phase.L3: 0
    }

    result = power_allocator.update_allocation(available_currents)

    # Verify results - both chargers should be reduced proportionally
    assert "charger1" in result
    assert "charger2" in result

    # charger1 uses 10A, charger2 uses 16A, total 26A
    # For Phase.L1: charger1 should get -10 * (10/26) = -3.85 ≈ -4
    # For Phase.L1: charger2 should get -10 * (16/26) = -6.15 ≈ -7
    assert result["charger1"][Phase.L1] == 6  # 10 - 4 = 6
    assert result["charger2"][Phase.L1] == 9  # 16 - 7 = 9


# ===== SINGLE PHASE POWER ALLOCATOR TESTS =====

def test_single_phase_power_allocation_overcurrent(power_allocator: PowerAllocator):
    """Test power allocation for single phase overcurrent scenario."""
    # Create and add a charger for single phase
    charger = MockCharger(initial_current=16, charger_id="charger1")
    charger.set_can_charge(True)
    power_allocator.add_charger_and_initialize(charger)

    # Simulate single phase overcurrent
    available_currents = {
        Phase.L1: -5,  # Only L1 phase is used
    }

    result = power_allocator.update_allocation(available_currents)

    # Verify results - charger should be reduced proportionally
    assert "charger1" in result
    assert result["charger1"] == {
        Phase.L1: 11,  # Reduced from 16 to 11 (16 + (-5) = 11)
        Phase.L2: 11,  # Synced phases should have same value
        Phase.L3: 11,
    }


def test_single_phase_power_allocation_recovery(power_allocator: PowerAllocator):
    """Test power allocation for single phase recovery scenario."""
    # Create and add a charger that's been reduced
    charger = MockCharger(initial_current=16, charger_id="charger1")
    charger.set_can_charge(True)
    # Set current limit lower than the requested limit
    charger.set_current_limits({
        Phase.L1: 10,
        Phase.L2: 10,
        Phase.L3: 10
    })
    power_allocator.add_charger_and_initialize(charger)

    # Make sure the power allocator knows the requested current
    power_allocator._chargers["charger1"].requested_current = {
        Phase.L1: 16,
        Phase.L2: 16,
        Phase.L3: 16
    }

    # Simulate single phase recovery with available capacity
    available_currents = {
        Phase.L1: 3,  # Only L1 phase is used
    }

    result = power_allocator.update_allocation(available_currents)

    # Verify results - charger should be increased proportionally
    assert "charger1" in result
    assert result["charger1"] == {
        Phase.L1: 13,  # Increased from 10 to 13 (10 + 3 = 13)
        Phase.L2: 13,  # Synced phases should have same value
        Phase.L3: 13,
    }


def test_single_phase_power_allocation_no_other_phases(power_allocator: PowerAllocator):
    """Test that single phase allocation ignores L2 and L3 phases."""
    # Create and add a charger
    charger = MockCharger(initial_current=16, charger_id="charger1")
    charger.set_can_charge(True)
    power_allocator.add_charger_and_initialize(charger)

    # Simulate single phase with only L1 data
    available_currents = {
        Phase.L1: -2,  # Only L1 phase provided
    }

    result = power_allocator.update_allocation(available_currents)

    # Should still work correctly with only L1 phase
    assert "charger1" in result
    assert result["charger1"] == {
        Phase.L1: 14,  # Reduced from 16 to 14
        Phase.L2: 14,  # Synced phases
        Phase.L3: 14,
    }


def test_single_phase_multiple_chargers_allocation(power_allocator: PowerAllocator):
    """Test power allocation for multiple chargers in single phase setup."""
    # Create and add two chargers
    charger1 = MockCharger(initial_current=16, charger_id="charger1")
    charger1.set_can_charge(True)
    charger2 = MockCharger(initial_current=12, charger_id="charger2")
    charger2.set_can_charge(True)

    power_allocator.add_charger_and_initialize(charger1)
    power_allocator.add_charger_and_initialize(charger2)

    # Simulate single phase overcurrent requiring 10A reduction total
    available_currents = {
        Phase.L1: -10,
    }

    result = power_allocator.update_allocation(available_currents)    # Verify both chargers are reduced proportionally
    assert "charger1" in result
    assert "charger2" in result

    # Actual proportional reduction based on current usage:
    # Total current = 16 + 12 = 28
    # Charger1 proportion: 16/28 = 4/7
    # Charger2 proportion: 12/28 = 3/7
    # Charger1 cut: floor(-10 * (4/7)) = floor(-5.71) = -6
    # Charger2 cut: floor(-10 * (3/7)) = floor(-4.29) = -5
    # Charger1 new: 16 + (-6) = 10
    # Charger2 new: 12 + (-5) = 7

    assert result["charger1"][Phase.L1] == 10  # 16 - 6 = 10
    assert result["charger2"][Phase.L1] == 7   # 12 - 5 = 7

    # All phases should be synced
    for phase in [Phase.L1, Phase.L2, Phase.L3]:
        assert result["charger1"][phase] == 10
        assert result["charger2"][phase] == 7


def test_single_phase_charger_state_initialization(power_allocator: PowerAllocator):
    """Test that charger state is properly initialized for single phase."""
    # Create and add a charger
    charger = MockCharger(initial_current=16, charger_id="charger1")
    charger.set_can_charge(True)

    success = power_allocator.add_charger_and_initialize(charger)

    assert success is True
    assert "charger1" in power_allocator._chargers

    state = power_allocator._chargers["charger1"]
    assert state.initialized is True
    assert state.requested_current == {
        Phase.L1: 16,
        Phase.L2: 16,
        Phase.L3: 16
    }
    assert state.last_applied_current == {
        Phase.L1: 16,
        Phase.L2: 16,
        Phase.L3: 16
    }


def test_single_phase_manual_override_detection(power_allocator: PowerAllocator):
    """Test manual override detection for single phase setup."""
    # Create and add a charger
    charger = MockCharger(initial_current=16, charger_id="charger1")
    charger.set_can_charge(True)
    power_allocator.add_charger_and_initialize(charger)

    # Apply some limits through the allocator
    power_allocator.update_applied_current(
        "charger1",
        {Phase.L1: 12, Phase.L2: 12, Phase.L3: 12},
        timestamp=int(time() - 30)   # make sure to pass the settle time
    )

    # Now simulate user manually changing the charger to different values
    charger.set_current_limits({
        Phase.L1: 14,
        Phase.L2: 14,
        Phase.L3: 14
    })

    # Get charger state and trigger manual override detection
    state = power_allocator._chargers["charger1"]
    state.detect_manual_override()

    # The override should be detected and requested current should be updated
    assert state.manual_override_detected is True
    assert state.requested_current == {
        Phase.L1: 14,
        Phase.L2: 14,
        Phase.L3: 14
    }
