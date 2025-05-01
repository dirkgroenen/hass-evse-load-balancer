"""
Simulation of the balancers for EVSE Load Balancing.

Use it to test and simulate the working of the balancer, based on a
short snippet of real-world data.
"""

from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

# For simulation we use our extracted OptimisedLoadBalancer class.
# Adjust the import path as needed.
from custom_components.evse_load_balancer.balancers.optimised_load_balancer import (
    OptimisedLoadBalancer,
)
from custom_components.evse_load_balancer.const import Phase

# Simulation constants
CURRENT_LIMIT = 25.0  # Used for overcurrent % calculations inside the balancer logic.
RAMP_DURATION = 15  # Duration (in simulation steps) over which ramping is applied.
MAX_CHARGE_CURRENT_PER_PHASE = 16.0  # Maximum per-phase current
INIT_CHARGE_CURRENT_PER_PHASE = 16.0  # Initial per-phase current

# Inladen van data
df_final_selected = pd.read_csv(
    Path.resolve(Path(__file__).parent / "simulation_data.csv"),
    index_col="last_changed",
    parse_dates=True,
)

# Create the OptimisedLoadBalancer using our simulation settings.
balancer = OptimisedLoadBalancer(
    recovery_window=900.0,
    trip_risk_threshold=60.0,
    risk_decay_per_second=1.0,
    recovery_risk_threshold=60 * 0.4,
    recovery_std=2.5,
)

# Initially, the charger current per phase is the maximum.
current_limits = dict.fromkeys(Phase, INIT_CHARGE_CURRENT_PER_PHASE)
max_limits = dict.fromkeys(Phase, MAX_CHARGE_CURRENT_PER_PHASE)

# For ramp simulation we store both start and target limits per phase and a
# common ramp counter.
ramp_start = current_limits.copy()
ramp_target = current_limits.copy()
ramp_time_left = 0  # Indicates if we are currently ramping.

# Logging lists for simulation plotting.
log_time = []
log_charger_limits = []
log_available_current = {phase: [] for phase in Phase}
log_events = []
stat_kwh_charged = 0.0

prev_timestamp = None

for timestamp, row in df_final_selected.iterrows():
    now = timestamp
    elapsed_seconds = (now - prev_timestamp).total_seconds() if prev_timestamp else 0

    # Determine charger load per phase from current limits (simulate charger demand)
    # In this simulation we assume the charger “draws” the set current.
    charger_load = {phase: current_limits[phase] for phase in Phase}

    # Calculate available current per phase based on measured corrected currents.
    # (Assuming row has keys: 'corrected_l1', 'corrected_l2', 'corrected_l3')
    available_currents = {
        Phase.L1: row["corrected_l1"] - charger_load[Phase.L1],
        Phase.L2: row["corrected_l2"] - charger_load[Phase.L2],
        Phase.L3: row["corrected_l3"] - charger_load[Phase.L3],
    }

    event = None

    # If we are in a ramping phase, update limits gradually.
    if ramp_time_left > 0:
        ramp_fraction = (RAMP_DURATION - ramp_time_left + 1) / RAMP_DURATION
        for phase in Phase:
            current_limits[phase] = (
                ramp_start[phase]
                + (ramp_target[phase] - ramp_start[phase]) * ramp_fraction
            )
        ramp_time_left -= 1

    # Not ramping: compute new limits using our OptimisedLoadBalancer.
    new_limits = balancer.compute_new_limits(
        current_limits, available_currents, max_limits, now=now.timestamp()
    )
    # If any phase changed, trigger a ramp by storing current limits as start and
    # new_limits as target.
    if ramp_time_left == 0 and any(
        new_limits[ph] != current_limits[ph] for ph in Phase
    ):
        ramp_start = current_limits.copy()
        ramp_target = new_limits.copy()
        ramp_time_left = RAMP_DURATION
        event = (
            "increase"
            if any(new_limits[ph] > current_limits[ph] for ph in Phase)
            else "decrease"
        )

    # Log outputs for plotting
    log_time.append(now)
    log_charger_limits.append(min(current_limits.values()))
    for phase in Phase:
        log_available_current[phase].append(available_currents[phase])
    log_events.append(event)

    # Calculate kWh charged (simple simulation: per-phase current * constant factor)
    # Here we assume 3 phases and a conversion factor (.23) from A to kW over the
    # sampled duration.
    for phase in Phase:
        stat_kwh_charged += (current_limits[phase] * 0.23) * (elapsed_seconds / 3600)

    prev_timestamp = now

# Prepare a DataFrame for plotting.
df_log = pd.DataFrame(
    {
        "timestamp": log_time,
        "charger_limit": log_charger_limits,
        Phase.L1: log_available_current[Phase.L1],
        Phase.L2: log_available_current[Phase.L2],
        Phase.L3: log_available_current[Phase.L3],
        "event": log_events,
    }
).set_index("timestamp")

# Plotting the simulation results.
fig, ax1 = plt.subplots(figsize=(18, 5))
ax1.plot(
    df_log.index,
    df_log[Phase.L1],
    label="Available L1 (A)",
    color="green",
    linewidth=1,
    alpha=0.7,
)
ax1.plot(
    df_log.index,
    df_log[Phase.L2],
    label="Available L2 (A)",
    color="orange",
    linewidth=1,
    alpha=0.7,
)
ax1.plot(
    df_log.index,
    df_log[Phase.L3],
    label="Available L3 (A)",
    color="purple",
    linewidth=1,
    alpha=0.7,
)
ax1.plot(
    df_log.index,
    df_log["charger_limit"],
    label="Charger Limit (A)",
    color="blue",
    linewidth=2,
    alpha=0.7,
)
ax1.set_ylabel("Charger Limit (A)")
ax1.set_xlabel("Time")
ax1.grid(visible=True)

# Indicate events when ramping occurs.
for idx, row in df_log[df_log["event"].notna()].iterrows():
    ax1.axvline(
        x=idx,
        color="green" if "increase" in row["event"] else "red",
        linestyle="--",
        alpha=0.6,
    )

fig.suptitle("Simulation of Charger Limits using OptimisedLoadBalancer")
ax1.legend(loc="upper left")
plt.tight_layout()
plt.show()
