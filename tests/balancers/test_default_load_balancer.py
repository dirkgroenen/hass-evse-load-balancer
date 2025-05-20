"""Test the Default Load Balancer."""

import time
from statistics import median

from custom_components.evse_load_balancer.balancers.default_load_balancer import DefaultLoadBalancer
from custom_components.evse_load_balancer.meters.meter import Phase

# Note: Adjust the import paths as needed to match your project structure.


def test_immediate_reduction():
    """
    Test that when available current is negative,
    the balancer immediately reduces the charger limit.
    """
    hysteresis_period = 300  # 5 minutes
    balancer = DefaultLoadBalancer(hysteresis_period=hysteresis_period)
    # Setup initial conditions
    # Current limits for each phase (e.g., in Amps)
    current_limits = {
        Phase.L1: 16,
        Phase.L2: 16,
        Phase.L3: 16,
    }
    # Available current for each phase is negative – we are over our limit.
    available_currents = {
        Phase.L1: -4,
        Phase.L2: -3,
        Phase.L3: -2,
    }
    # Maximum limits per phase
    max_limits = {
        Phase.L1: 32,
        Phase.L2: 32,
        Phase.L3: 32,
    }
    # Simulate time (ensure hysteresis period has passed for immediate reduction)
    now = time.time() + hysteresis_period + 1

    new_limits = balancer.compute_availability(current_limits, available_currents, max_limits, now=now)
    # Expect that each phase is reduced immediately: new_limit = current + available_current (clamped to non-negative).
    assert new_limits[Phase.L1] == max(0, current_limits[Phase.L1] + available_currents[Phase.L1])
    assert new_limits[Phase.L2] == max(0, current_limits[Phase.L2] + available_currents[Phase.L2])
    assert new_limits[Phase.L3] == max(0, current_limits[Phase.L3] + available_currents[Phase.L3])


def test_buffered_increase():
    """
    Test that when available current is positive,
    the balancer buffers increases until the hysteresis period has elapsed.
    """
    hysteresis_period = 300  # 5 minutes in seconds
    balancer = DefaultLoadBalancer(hysteresis_period=hysteresis_period)
    current_limits = {
        Phase.L1: 16,
        Phase.L2: 16,
        Phase.L3: 16,
    }
    max_limits = {
        Phase.L1: 32,
        Phase.L2: 32,
        Phase.L3: 32,
    }
    # Define available current for each phase.
    available_currents = {
        Phase.L1: 4,
        Phase.L2: 3,
        Phase.L3: 2,
    }

    # Simulate repeated calls within the hysteresis period (e.g., every 10 seconds),
    # so that the buffer is populated.
    start_time = time.time()
    # Number of calls to simulate (e.g., 5 calls over 40 seconds).
    num_calls = 5
    for i in range(num_calls):
        current_time = start_time + i * 10  # every 10 seconds
        # Call compute_availability; it won't flush because hysteresis_period hasn't elapsed.
        _ = balancer.compute_availability(current_limits, available_currents, max_limits, now=current_time)

    # Now, simulate a final call after the hysteresis period has elapsed.
    final_time = start_time + hysteresis_period + 1
    new_limits = balancer.compute_availability(current_limits, available_currents, max_limits, now=final_time)

    # The buffered values for each phase should be [available_current]*num_calls.
    # Thus, the median for Phase.L1 is median([4,4,4,4,4]) which is 4, etc.
    expected_L1 = min(max_limits[Phase.L1], current_limits[Phase.L1] + int(median([available_currents[Phase.L1]] * num_calls)))
    expected_L2 = min(max_limits[Phase.L2], current_limits[Phase.L2] + int(median([available_currents[Phase.L2]] * num_calls)))
    expected_L3 = min(max_limits[Phase.L3], current_limits[Phase.L3] + int(median([available_currents[Phase.L3]] * num_calls)))

    assert new_limits[Phase.L1] == expected_L1, f"Expected {expected_L1}, got {new_limits[Phase.L1]}"
    assert new_limits[Phase.L2] == expected_L2, f"Expected {expected_L2}, got {new_limits[Phase.L2]}"
    assert new_limits[Phase.L3] == expected_L3, f"Expected {expected_L3}, got {new_limits[Phase.L3]}"
