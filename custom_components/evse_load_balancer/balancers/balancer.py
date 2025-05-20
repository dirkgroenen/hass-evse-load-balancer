"""Abstract Balancer Base Class for Load Balancing Algorithms."""

from abc import ABC, abstractmethod
from time import time

from ..meters.meter import Phase  # noqa: TID252


class Balancer(ABC):
    """Abstract base class for a load balancing algorithm."""

    @abstractmethod
    def compute_availability(
        self,
        current_limits: dict[Phase, int],
        available_currents: dict[Phase, int],
        max_limits: dict[Phase, int],
        now: float = time(),
    ) -> dict[Phase, int]:
        """
        Compute new charger limits.

        :param current_limits: The current settings on the charger.
        :param available_currents: The available current per phase.
        :param max_limits: The maximum allowed per phase.
        :return: New limits per phase.
        """
        raise NotImplementedError
