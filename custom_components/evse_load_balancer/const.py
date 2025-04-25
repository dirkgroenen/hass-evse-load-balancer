"""Constants for the evse-load-balancer integration."""

from enum import Enum

DOMAIN = "evse_load_balancer"

CHARGER_DOMAIN_EASEE = "easee"
SUPPORTED_CHARGER_DEVICE_DOMAINS = (CHARGER_DOMAIN_EASEE,)

METER_DOMAIN_DSMR = "dsmr"
SUPPORTED_METER_DEVICE_DOMAINS = (METER_DOMAIN_DSMR,)


COORDINATOR_STATE_AWAITING_CHARGER = "awaiting_charger"
COORDINATOR_STATE_MONITORING_LOAD = "monitoring_loads"
COORDINATOR_STATES: tuple[str] = (
    COORDINATOR_STATE_AWAITING_CHARGER,
    COORDINATOR_STATE_MONITORING_LOAD,
)

EVSE_LOAD_BALANCER_COORDINATOR_EVENT = "evse_load_balancer_coordinator_event"
EVENT_ACTION_NEW_CHARGER_LIMITS = "new_charger_limits"
EVENT_ATTR_ACTION = "action"
EVENT_ATTR_NEW_LIMITS = "new_limits"


class Phase(Enum):
    """Enum for the phases."""

    L1 = "l1"
    L2 = "l2"
    L3 = "l3"
