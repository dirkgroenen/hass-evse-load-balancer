import logging
from pathlib import Path

import matplotlib.pyplot as plt
import pandas as pd

from custom_components.evse_load_balancer.balancers.optimised_load_balancer import (
    OptimisedLoadBalancer,
)
from custom_components.evse_load_balancer.chargers.charger import Charger
from custom_components.evse_load_balancer.const import Phase
from custom_components.evse_load_balancer.power_allocator import PowerAllocator

logging.basicConfig(level=logging.INFO)
_LOGGER = logging.getLogger(__name__)

# Simulation constants
FUSE_SIZE = 25.0
MAX_CHARGE_CURRENT_PER_PHASE = 16.0


class FakeCharger(Charger):
    """A fake charger for simulation purposes."""

    def __init__(self):
        self._current_limit = dict.fromkeys(Phase, 0)
        self._max_limit = dict.fromkeys(Phase, MAX_CHARGE_CURRENT_PER_PHASE)

    @property
    def id(self) -> str:
        return "fake_charger"

    def can_charge(self) -> bool:
        return True

    def car_connected(self) -> bool:
        return True

    def get_current_limit(self) -> dict[Phase, float]:
        return dict(self._current_limit)

    def get_max_current_limit(self) -> dict[Phase, float]:
        return dict(self._max_limit)

    def has_synced_phase_limits(self) -> bool:
        return True

    def set_current_limit(self, limit) -> None:
        self._current_limit = dict(limit)

    def set_phase_mode(self, mode, phase):
        pass


# Load CSV data
df = pd.read_csv(
    Path.resolve(Path(__file__).parent / "simulation_data.csv"),
    index_col="last_changed",
    parse_dates=True,
)

# Setup simulation objects
balancer = OptimisedLoadBalancer()
allocator = PowerAllocator()
charger = FakeCharger()
allocator.add_charger(charger)

# Initial state
current_limits = dict.fromkeys(Phase, MAX_CHARGE_CURRENT_PER_PHASE)
max_limits = dict.fromkeys(Phase, FUSE_SIZE)
prev_timestamp = None

log_time = []
log_charger_limits = []
log_computed_current = {phase: [] for phase in Phase}
log_available_current = {phase: [] for phase in Phase}
stat_kwh_charged = 0.0

_previous_computed_current = None

for timestamp, row in df.iterrows():
    now = timestamp
    elapsed_seconds = (now - prev_timestamp).total_seconds() if prev_timestamp else 0

    # Simulate charger load per phase
    charger_load = {phase: charger.get_current_limit()[phase] for phase in Phase}

    # Calculate available current per phase
    available_currents = {
        Phase.L1: row["corrected_l1"] - charger_load[Phase.L1],
        Phase.L2: row["corrected_l2"] - charger_load[Phase.L2],
        Phase.L3: row["corrected_l3"] - charger_load[Phase.L3],
    }

    # Balancer computes phase deltas
    computed_availability = balancer.compute_availability(
        available_currents=available_currents,
        max_limits=max_limits,
        now=now.timestamp(),
    )

    if _previous_computed_current != computed_availability:
        _previous_computed_current = computed_availability

        # PowerAllocator distributes available current
        allocation_results = allocator.update_allocation(computed_availability)
        allocation_result = allocation_results.get(charger.id, None)

        # Apply new limits if needed
        if allocation_result:
            _LOGGER.info("Setting new current limit for charger %s: %s", charger.id, allocation_result)
            charger.set_current_limit(allocation_result)
            allocator.update_applied_current(
                charger_id=charger.id,
                applied_current=allocation_result,
                timestamp=now.timestamp(),
            )

    # Logging for analysis
    log_time.append(now)
    log_charger_limits.append(min(charger.get_current_limit().values()))
    for phase in Phase:
        log_available_current[phase].append(available_currents[phase])

    for phase in Phase:
        log_computed_current[phase].append(computed_availability[phase])

    # Calculate kWh charged (simple simulation)
    for phase in Phase:
        stat_kwh_charged += (charger.get_current_limit()[phase] * 0.23) * (elapsed_seconds / 3600)

    prev_timestamp = now

# Optionally, plot results as in your original script

df_log = pd.DataFrame(
    {
        "timestamp": log_time,
        "charger_limit": log_charger_limits,
        Phase.L1: log_available_current[Phase.L1],
        Phase.L2: log_available_current[Phase.L2],
        Phase.L3: log_available_current[Phase.L3],
        "Computed L1": log_computed_current[Phase.L1],
        "Computed L2": log_computed_current[Phase.L2],
        "Computed L3": log_computed_current[Phase.L3],
    }
).set_index("timestamp")

fig, ax1 = plt.subplots(figsize=(18, 5))
ax1.plot(df_log.index, df_log[Phase.L1], label="Available L1 (A)", color="green", linewidth=1, alpha=0.7)
ax1.plot(df_log.index, df_log[Phase.L2], label="Available L2 (A)", color="orange", linewidth=1, alpha=0.7)
ax1.plot(df_log.index, df_log[Phase.L3], label="Available L3 (A)", color="purple", linewidth=1, alpha=0.7)
ax1.plot(df_log.index, df_log["Computed L1"], label="Computed L1 (A)", color="green", linewidth=1, alpha=0.5, linestyle="--")
ax1.plot(df_log.index, df_log["Computed L2"], label="Computed L2 (A)", color="orange", linewidth=1, alpha=0.5, linestyle="--")
ax1.plot(df_log.index, df_log["Computed L3"], label="Computed L3 (A)", color="purple", linewidth=1, alpha=0.5, linestyle="--")
ax1.plot(df_log.index, df_log["charger_limit"], label="Charger Limit (A)", color="blue", linewidth=2, alpha=0.7)
ax1.set_ylabel("Charger Limit (A)")
ax1.set_xlabel("Time")
ax1.grid(visible=True)
fig.suptitle("Simulation of Charger Limits using Coordinator Logic")
ax1.legend(loc="upper left")
plt.tight_layout()
plt.show()
