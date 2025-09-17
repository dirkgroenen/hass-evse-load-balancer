"""Abstract Balancer Base Class for Load Balancing Algorithms."""

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
        max_limits: dict[Phase, int],
        trip_risk_threshold: int = 60,  # Allowed risk before reducing the limit
        risk_decay_per_second: float = 1.0,  # How quickly accumulated risk decays
    ) -> None:
        """Initialize the load balancer."""
        self._phase_monitors = {
            phase: PhaseMonitor(
                phase=phase,
                max_limit=max_limits[phase],
                trip_risk_threshold=trip_risk_threshold,
                risk_decay_per_second=risk_decay_per_second,
            )
            for phase in max_limits
        }

    def compute_availability(
        self,
        available_currents: dict[Phase, int],
        now: float = time(),
    ) -> dict[Phase, int]:
        """Compute available currents."""
        available = {}
        for phase, current in available_currents.items():
            available[phase] = self._phase_monitors[phase].update(
                avail=current, now=now
            )
        return available


class PhaseMonitor:
    """Monitor a single phase."""

    def __init__(
        self,
        phase: Phase,
        max_limit: int,
        trip_risk_threshold: int = 60,
        risk_decay_per_second: float = 1.0,
    ) -> None:
        """Monitor given phase current availability and return normalised limits."""
        self.phase = phase
        self.max_limit = max_limit
        self.phase_limit = max_limit  # Initial limit is the maximum limit
        self._trip_risk_threshold = trip_risk_threshold
        self._risk_decay_per_second = risk_decay_per_second

        self._last_compute: int | None = None
        self._cumulative_trip_risk = 0.0

    def update(self, avail: float, now: int) -> float:
        """Update the current availability and compute the new limit."""
        elapsed = now - self._last_compute if self._last_compute is not None else 0

        # Multiplicative decrease on overcurrent
        if avail < 0:
            risk_increase = self._calculate_trip_risk(avail) * elapsed
            self._cumulative_trip_risk += risk_increase

            # If risk exceeds threshold, multiplicative reduction of power
            if self._cumulative_trip_risk >= self._trip_risk_threshold:
                self._cumulative_trip_risk = 0.0
                self.phase_limit = avail
        # Additive increase when line is stable
        else:
            risk_decay = self._risk_decay_per_second * elapsed
            self._cumulative_trip_risk = max(
                0.0, self._cumulative_trip_risk - risk_decay
            )
            self.phase_limit = min(self.max_limit, avail)

        self._last_compute = now

        return self.phase_limit

    def _calculate_trip_risk(self, available: float) -> float:
        """
        Calculate trip risk factor based on overcurrent percentage.

        Overcurrent percentage is a value between 0 and 1
        and the returned value is a fraction of the trip risk threshold
        devided by the number of seconds the overcurrency is allowed.
        the values here are roughly (as in extremely roughly) based on
        the trip risk curve in C-character circuit breakers.
        """
        overcurrent_percentage = abs(available) / self.max_limit
        if overcurrent_percentage <= 0.13:  # noqa: PLR2004
            return self._trip_risk_threshold / 60
        if overcurrent_percentage <= 0.40:  # noqa: PLR2004
            return self._trip_risk_threshold / 30
        if overcurrent_percentage <= 1.0:
            return self._trip_risk_threshold / 10
        return self._trip_risk_threshold
