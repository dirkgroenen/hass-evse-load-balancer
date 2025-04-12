"""Constants for the evse-load-balancer integration."""
from enum import Enum

DOMAIN = "evse_load_balancer"

CHARGER_DOMAIN_EASEE = "easee"
SUPPORTED_CHARGER_DEVICE_DOMAINS = (
    CHARGER_DOMAIN_EASEE,
)

METER_DOMAIN_DSMR = "dsmr"
SUPPORTED_METER_DEVICE_DOMAINS = (
    METER_DOMAIN_DSMR,
)


class Phase(Enum):
    L1 = "l1"
    L2 = "l2"
    L3 = "l3"
