from custom_components.evse_load_balancer.balancers.optimised_load_balancer import OptimisedLoadBalancer, PhaseMonitor
from custom_components.evse_load_balancer.const import OvercurrentMode, Phase


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


def test_conservative_mode_init():
    lb = OptimisedLoadBalancer(
        max_limits=dict.fromkeys(Phase, 25),
        overcurrent_mode=OvercurrentMode.CONSERVATIVE,
    )
    for controller in lb._phase_monitors:
        assert isinstance(lb._phase_monitors[controller], PhaseMonitor)
        assert lb._phase_monitors[controller]._overcurrent_mode == OvercurrentMode.CONSERVATIVE
        assert lb._phase_monitors[controller].max_limit == 25
        assert lb._phase_monitors[controller].phase_limit == 25


def test_conservative_mode_immediate_reduction():
    lb = OptimisedLoadBalancer(
        max_limits=dict.fromkeys(Phase, 25),
        overcurrent_mode=OvercurrentMode.CONSERVATIVE,
    )
    available_currents_one = {phase: 20 for phase in Phase}
    available_currents_two = {phase: -5 for phase in Phase}
    now = 100

    limits_one = lb.compute_availability(available_currents_one, 0)
    limits_two = lb.compute_availability(available_currents_two, now)

    for phase in Phase:
        assert limits_one[phase] == 20
        assert limits_two[phase] == 15


def test_conservative_mode_never_goes_below_zero():
    lb = OptimisedLoadBalancer(
        max_limits=dict.fromkeys(Phase, 25),
        overcurrent_mode=OvercurrentMode.CONSERVATIVE,
    )
    available_currents_one = {phase: 5 for phase in Phase}
    available_currents_two = {phase: -10 for phase in Phase}

    limits_one = lb.compute_availability(available_currents_one, 0)
    limits_two = lb.compute_availability(available_currents_two, 100)

    for phase in Phase:
        assert limits_one[phase] == 5
        assert limits_two[phase] == 0


def test_conservative_mode_allows_increases():
    lb = OptimisedLoadBalancer(
        max_limits=dict.fromkeys(Phase, 25),
        overcurrent_mode=OvercurrentMode.CONSERVATIVE,
    )
    available_currents_one = {phase: 10 for phase in Phase}
    available_currents_two = {phase: -5 for phase in Phase}
    available_currents_three = {phase: 15 for phase in Phase}

    limits_one = lb.compute_availability(available_currents_one, 0)
    limits_two = lb.compute_availability(available_currents_two, 100)
    limits_three = lb.compute_availability(available_currents_three, 200)

    for phase in Phase:
        assert limits_one[phase] == 10
        assert limits_two[phase] == 5
        assert limits_three[phase] == 15


def test_conservative_mode_risk_not_accumulated():
    lb = OptimisedLoadBalancer(
        max_limits=dict.fromkeys(Phase, 25),
        overcurrent_mode=OvercurrentMode.CONSERVATIVE,
    )
    available_currents = {phase: -2 for phase in Phase}

    lb.compute_availability(available_currents, 0)
    lb.compute_availability(available_currents, 10)
    lb.compute_availability(available_currents, 20)

    for phase in Phase:
        assert lb._phase_monitors[phase]._cumulative_trip_risk == 0.0


def test_optimised_mode_default_allows_temporary_overcurrent():
    lb = OptimisedLoadBalancer(max_limits=dict.fromkeys(Phase, 25))
    for controller in lb._phase_monitors:
        assert lb._phase_monitors[controller]._overcurrent_mode == OvercurrentMode.OPTIMISED


def test_conservative_vs_optimised_mode_behavior():
    lb_conservative = OptimisedLoadBalancer(
        max_limits=dict.fromkeys(Phase, 25),
        overcurrent_mode=OvercurrentMode.CONSERVATIVE,
    )
    lb_optimised = OptimisedLoadBalancer(
        max_limits=dict.fromkeys(Phase, 25),
        overcurrent_mode=OvercurrentMode.OPTIMISED,
    )

    available_one = {phase: 20 for phase in Phase}
    available_two = {phase: -3 for phase in Phase}

    limits_conservative_one = lb_conservative.compute_availability(available_one, 0)
    limits_optimised_one = lb_optimised.compute_availability(available_one, 0)

    limits_conservative_two = lb_conservative.compute_availability(available_two, 5)
    limits_optimised_two = lb_optimised.compute_availability(available_two, 5)

    for phase in Phase:
        assert limits_conservative_one[phase] == 20
        assert limits_optimised_one[phase] == 20
        assert limits_conservative_two[phase] == 17
        assert limits_optimised_two[phase] == 20
