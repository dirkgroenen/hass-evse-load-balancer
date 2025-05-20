"""Default Load Balancer Algorithm."""

from statistics import median
from time import time

from ..meters.meter import Phase  # noqa: TID252
from .balancer import Balancer


class DefaultLoadBalancer(Balancer):
    """
    Default load balancer algorithm.

    Immediately reduces the charger limit when available current is negative.
    When positive, it delays increases, smoothing the value over a set period.
    """

    def __init__(self, hysteresis_period: int = 5 * 60) -> None:
        """Init."""
        self.hysteresis_period = hysteresis_period  # seconds
        self._buffers: dict[Phase, list[int]] = {phase: [] for phase in Phase}
        self._last_update: dict[Phase, float] = dict.fromkeys(Phase, 0.0)
        self._hysteresis_start = dict.fromkeys(Phase)
        self._hysteresis_buffer = dict.fromkeys(Phase)

    def compute_availability(
        self,
        current_limits: dict[Phase, int],
        available_currents: dict[Phase, int],
        max_limits: dict[Phase, int],
        now: float = time(),
    ) -> dict[Phase, int]:
        """Compute current limits limits."""
        new_limits = current_limits.copy()
        for phase in Phase:
            avail = available_currents[phase]
            current = current_limits[phase]
            max_limit = max_limits[phase]
            # Immediate reduction if consumption is over the limit:
            if avail < 0:
                new_val = max(0, current + avail)
                new_limits[phase] = new_val

                self._reset_hysteresis(phase)
                self._last_update[phase] = now
            else:
                # Buffer the available current for positive adjustments.
                self._buffers[phase].append(avail)
                # Increase only if the hysteresis period has passed.
                if now - self._last_update[phase] >= self.hysteresis_period:
                    # Use median of buffered values for a "sustained" positive value.
                    median_incr = int(median(self._buffers[phase]))
                    new_val = min(max_limit, current + median_incr)
                    new_limits[phase] = new_val
                    self._buffers[phase].clear()
                    self._last_update[phase] = now

        return new_limits

    def _apply_phase_hysteresis(
        self, phase: Phase, available_current: int
    ) -> int | None:
        """Apply hysteresis to the current limit for a given phase."""
        now = int(time())
        if self._hysteresis_start[phase] is None:
            self._hysteresis_start[phase] = now
            self._hysteresis_buffer[phase] = []

        buffer = self._hysteresis_buffer[phase]
        start_time = self._hysteresis_start[phase]

        buffer.append(available_current)
        elapsed_min = (now - start_time) / 60

        if elapsed_min >= self.hysteresis_period:
            smoothened_current = int(median(self._hysteresis_buffer[phase]))
            self._reset_hysteresis(phase)
            return smoothened_current

        return None

    def _reset_hysteresis(self, phase: Phase) -> None:
        self._hysteresis_start[phase] = None
        self._hysteresis_buffer[phase] = []
