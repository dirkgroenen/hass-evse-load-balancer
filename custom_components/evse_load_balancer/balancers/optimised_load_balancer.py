"""Abstract Balancer Base Class for Load Balancing Algorithms."""

from collections import deque
from statistics import median, pstdev
from time import time

from ..meters.meter import Phase  # noqa: TID252
from .balancer import Balancer


class OptimisedLoadBalancer(Balancer):
    """
    Optimised variant of the default Load Balancer.

    This one is less aggressive in reducing and increasing the limits.
    It allows spikes to happen without immediate action, and is a bit
    more relaxed in increasing the limits again to prevent hysteresis.

    On the other hand, it does put a bit more load on your circuit, as it
    accepts temporary overcurrent situations, and only reduces the limits
    when the risk is high enough.
    """

    def __init__(
        self,
        recovery_window: float = 900.0,  # seconds over which recovery is buffered.
        trip_risk_threshold: float = 60.0,  # risk value threshold to trigger reduction.
        risk_decay_per_second: float = 1.0,  # how quickly accumulated risk decays.
        recovery_risk_threshold: float = 60
        * 0.4,  # threshold for considering recovery stable.
        recovery_std: float = 2.5,  # maximum std dev allowed in recovery measurements.
    ) -> None:
        """Initialize the optimised load balancer."""
        self._recovery_current_history = {
            phase: deque(maxlen=int(recovery_window)) for phase in Phase
        }
        self._recovery_risk_history = {
            phase: deque(maxlen=int(recovery_window)) for phase in Phase
        }
        self._cumulative_trip_risk = dict.fromkeys(Phase, 0.0)
        self._last_adjustment_time = dict.fromkeys(Phase, 0)
        self._last_compute = 0

        self.recovery_window = recovery_window
        self.trip_risk_threshold = trip_risk_threshold
        self.risk_decay_per_second = risk_decay_per_second
        self.recovery_risk_threshold = recovery_risk_threshold
        self.recovery_std = recovery_std

        self._last_computed_availability = {}

    def compute_availability(
        self,
        available_currents: dict[Phase, int],
        max_limits: dict[Phase, int],
        now: float = time(),
    ) -> dict[Phase, int]:
        """Compute available currents."""
        new_limits = {}
        elapsed = now - self._last_compute

        for phase, avail in available_currents.items():
            max_limit = max_limits[phase]
            new_target = self._last_computed_availability.get(phase, avail)

            # 1) overcurrent - accumulate risk & handle reduction of current
            if avail < 0:
                overcurrent_percentage = abs(avail) / max_limit
                risk_increase = (
                    self.calculate_trip_risk(overcurrent_percentage) * elapsed
                )
                self._cumulative_trip_risk[phase] += risk_increase
                self._recovery_risk_history[phase].append(risk_increase)

                # If risk exceeds threshold, immediately reduce power setting.
                if self._cumulative_trip_risk[phase] >= self.trip_risk_threshold:
                    new_target = avail
                    self._last_adjustment_time[phase] = now
                    self._recovery_current_history[phase].clear()
                    self._recovery_risk_history[phase].clear()
                    self._cumulative_trip_risk[phase] = 0.0
            # 2) availability - decay risk and handle recovery of current
            else:
                risk_decay = self.risk_decay_per_second * elapsed
                self._cumulative_trip_risk[phase] = max(
                    0.0, self._cumulative_trip_risk[phase] - risk_decay
                )
                self._recovery_current_history[phase].append(avail)
                self._recovery_risk_history[phase].append(-risk_decay)

                # If enough time has passed and the current setting is below maximum,
                # consider increasing the power setting after stable recovery.
                if now - self._last_adjustment_time[
                    phase
                ] >= self.recovery_window and self.is_stable_recovery(
                    self._recovery_risk_history[phase]
                ):
                    # Ensure stability via standard deviation.
                    std_val = pstdev(self._recovery_current_history[phase])
                    if std_val < self.recovery_std:
                        new_target = median(self._recovery_current_history[phase])
                        self._last_adjustment_time[phase] = now
                        self._recovery_current_history[phase].clear()
                        self._recovery_risk_history[phase].clear()
                        self._cumulative_trip_risk[phase] = 0.0

            # New limit is max current scaled by the current power setting.
            new_limits[phase] = new_target

        self._last_computed_availability = new_limits.copy()
        self._last_compute = now
        return new_limits

    def calculate_trip_risk(self, overcurrent_percentage: float) -> float:
        """
        Calculate trip risk factor based on overcurrent percentage.

        Overcurrent percentage is a value between 0 and 1
        and the returned value is a fraction of the trip risk threshold
        devided by the number of seconds the overcurrency is allowed.
        the values here are roughly (as in extremely roughly) based on
        the trip risk curve in C-character circuit breakers.
        """
        if overcurrent_percentage <= 0.13:  # noqa: PLR2004
            return self.trip_risk_threshold / 60
        if overcurrent_percentage <= 0.40:  # noqa: PLR2004
            return self.trip_risk_threshold / 30
        if overcurrent_percentage <= 1.0:
            return self.trip_risk_threshold / 10
        return self.trip_risk_threshold

    def is_stable_recovery(self, history: deque) -> bool:
        """Is recovery stable based on the history of available currents."""
        return sum(history) <= self.recovery_risk_threshold if history else False
