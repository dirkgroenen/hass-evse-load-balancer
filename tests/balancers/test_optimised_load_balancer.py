from collections import deque
from custom_components.evse_load_balancer.balancers.optimised_load_balancer import OptimisedLoadBalancer
from custom_components.evse_load_balancer.const import Phase


def test_default_init():
    lb = OptimisedLoadBalancer()
    # Check that instance variables are set properly.
    assert lb.recovery_window == 900.0
    assert lb.trip_risk_threshold == 60.0
    assert lb.risk_decay_per_second == 1.0
    assert lb.recovery_risk_threshold == 60 * 0.4
    assert lb.recovery_std == 2.5
    for phase in Phase:
        assert isinstance(lb._recovery_current_history[phase], deque) is True
        assert lb._recovery_current_history[phase].maxlen == int(900.0)
        assert lb._cumulative_trip_risk[phase] == 0.0
        assert lb._last_adjustment_time[phase] == 0.0


def test_negative_available_current_triggers_reduction():
    lb = OptimisedLoadBalancer()
    available_currents_one = {phase: 10 for phase in Phase}
    available_currents_two = {phase: -5 for phase in Phase}
    max_limits = {phase: 32 for phase in Phase}
    now = 100
    lb.compute_availability(available_currents_one, max_limits, 0)
    computed_availability = lb.compute_availability(available_currents_two, max_limits, now)
    # Calculation:
    # overcurrent_percentage = abs(-5)/32 ~ 0.15625 => risk increase rate = 60/30 = 2.
    # risk_increase = 2 * (100) = 200, which exceeds trip_risk_threshold (60).
    # Therefore, the returned available current should be -5.
    for phase in Phase:
        assert computed_availability[phase] == -5
        # Check that the history is cleared and cumulative risk reset.
        assert len(lb._recovery_current_history[phase]) == 0
        assert lb._cumulative_trip_risk[phase] == 0.0
        assert lb._last_adjustment_time[phase] == now


def test_negative_available_current_within_risk_boundary():
    lb = OptimisedLoadBalancer()
    available_currents_one = {phase: 5 for phase in Phase}
    available_currents_two = {phase: -5 for phase in Phase}
    max_limits = {phase: 32 for phase in Phase}
    now = 5
    lb.compute_availability(available_currents_one, max_limits, 0)
    computed_availability = lb.compute_availability(available_currents_two, max_limits, now)
    # Calculation:
    # overcurrent_percentage = abs(-5)/32 ~ 0.15625 => risk increase rate = 60/30 = 2.
    # risk_increase = 2 * (5) = 10, which is less than trip_risk_threshold (60).
    # Therefore, the returned available current should be -5.
    for phase in Phase:
        assert computed_availability[phase] == 5
        # Check if added to risk history
        assert len(lb._recovery_current_history[phase]) == 1
        assert lb._cumulative_trip_risk[phase] == 10.0
        assert lb._last_adjustment_time[phase] == 0


def test_positive_available_current_no_change_before_recovery():
    lb = OptimisedLoadBalancer()
    # When available current is positive but not enough time for recovery, limits remain unchanged.
    available_currents = {phase: 5 for phase in Phase}
    max_limits = {phase: 30 for phase in Phase}
    now = 100  # elapsed is 100, which is less than recovery_window (900)
    new_limits = lb.compute_availability(available_currents, max_limits, now)
    # In this branch, the risk decays and available current is buffered.
    for phase in Phase:
        # No update should occur; limit remains same.
        assert new_limits[phase] == 5
        # The recovery history should now contain the appended available current.
        assert 5 in lb._recovery_current_history[phase]
        # Cumulative risk remains at 0 after decay.
        assert lb._cumulative_trip_risk[phase] == 0.0
        # Last adjustment time remains unchanged.
        assert lb._last_adjustment_time[phase] == 0.0


def test_stable_recovery_triggers_increase():
    lb = OptimisedLoadBalancer()
    # Setup a scenario where recovery is stable and enough time has elapsed.
    available_currents = {phase: 5 for phase in Phase}
    max_limits = {phase: 30 for phase in Phase}
    # Manually pre-populate recovery history to simulate stable recovery.
    for phase in Phase:
        lb._recovery_current_history[phase] = deque([5, 5, 5], maxlen=int(lb.recovery_window))
        # Set last adjustment time to 0 to force elapsed time.
        lb._last_adjustment_time[phase] = 0.0
    now = 1000  # elapsed (1000 seconds) is >= recovery_window (900)
    new_limits = lb.compute_availability(available_currents, max_limits, now)
    for phase in Phase:
        assert new_limits[phase] == 5
        assert len(lb._recovery_current_history[phase]) == 0
        assert lb._cumulative_trip_risk[phase] == 0.0
        assert lb._last_adjustment_time[phase] == now


def test_calculate_trip_risk():
    lb = OptimisedLoadBalancer()
    # Test the trip risk calculation for various overcurrent percentages.
    assert lb.calculate_trip_risk(0.1) == 60.0 / 60
    assert lb.calculate_trip_risk(0.2) == 60.0 / 30
    assert lb.calculate_trip_risk(0.8) == 60.0 / 10
    assert lb.calculate_trip_risk(1.2) == 60.0
