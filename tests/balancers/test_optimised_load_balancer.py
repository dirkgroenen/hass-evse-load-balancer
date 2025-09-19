from custom_components.evse_load_balancer.balancers.optimised_load_balancer import OptimisedLoadBalancer, PhaseMonitor
from custom_components.evse_load_balancer.const import Phase


def test_default_init():
    lb = OptimisedLoadBalancer(max_limits=dict.fromkeys(Phase, 25))
    for controller in lb._phase_monitors:
        assert isinstance(lb._phase_monitors[controller], PhaseMonitor)
        # Check that the default values are set correctly.
        assert lb._phase_monitors[controller]._trip_risk_threshold == 60
        assert lb._phase_monitors[controller]._risk_decay_per_second == 1.0
        assert lb._phase_monitors[controller].max_limit == 25
        assert lb._phase_monitors[controller].phase_limit == 25


def test_negative_available_current_triggers_reduction():
    lb = OptimisedLoadBalancer(max_limits=dict.fromkeys(Phase, 25))
    available_currents_one = {phase: 10 for phase in Phase}
    available_currents_two = {phase: -5 for phase in Phase}
    now = 100
    lb.compute_availability(available_currents_one, 0)
    computed_availability = lb.compute_availability(available_currents_two, now)
    # Calculation:
    # overcurrent_percentage = abs(-5)/32 ~ 0.15625 => risk increase rate = 60/30 = 2.
    # risk_increase = 2 * (100) = 200, which exceeds trip_risk_threshold (60).
    # Therefore, the returned available current should be -5.
    for phase in Phase:
        assert computed_availability[phase] == -5


def test_negative_available_current_within_risk_boundary():
    lb = OptimisedLoadBalancer(max_limits=dict.fromkeys(Phase, 25))
    available_currents_one = {phase: 5 for phase in Phase}
    available_currents_two = {phase: -5 for phase in Phase}
    now = 5
    lb.compute_availability(available_currents_one, 0)
    computed_availability = lb.compute_availability(available_currents_two, now)
    # Calculation:
    # overcurrent_percentage = abs(-5)/32 ~ 0.15625 => risk increase rate = 60/30 = 2.
    # risk_increase = 2 * (5) = 10, which is less than trip_risk_threshold (60).
    # Therefore, the returned available current should be -5.
    for phase in Phase:
        assert computed_availability[phase] == 5


def test_stable_recovery_triggers_increase():
    lb = OptimisedLoadBalancer(max_limits=dict.fromkeys(Phase, 25))
    # Setup a scenario where recovery is stable and enough time has elapsed.
    available_currents = {phase: 5 for phase in Phase}
    now = 100  # elapsed (100 seconds)
    new_limits = lb.compute_availability(available_currents, now)
    for phase in Phase:
        assert new_limits[phase] == 5


def test_calculate_trip_risk():
    lb = OptimisedLoadBalancer(max_limits=dict.fromkeys(Phase, 25))
    pm = lb._phase_monitors[Phase.L1]
    # Test the trip risk calculation for various overcurrent percentages.
    assert pm._calculate_trip_risk(-2) == 60.0 / 60
    assert pm._calculate_trip_risk(-10) == 60.0 / 30
    assert pm._calculate_trip_risk(-15) == 60.0 / 10
    assert pm._calculate_trip_risk(-35) == 60.0
