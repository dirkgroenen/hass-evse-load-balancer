"""Constants for the evse-load-balancer integration."""

from enum import Enum

DOMAIN = "evse_load_balancer"

CHARGER_DOMAIN_EASEE = "easee"
CHARGER_DOMAIN_ZAPTEC = "zaptec"
CHARGER_DOMAIN_LEKTRICO = "lektrico"
CHARGER_DOMAIN_KEBA = "keba"
CHARGER_DOMAIN_WALLBOX = "wallbox"

HA_INTEGRATION_DOMAIN_MQTT = "mqtt"
Z2M_DEVICE_IDENTIFIER_DOMAIN = "zigbee2mqtt"
CHARGER_MANUFACTURER_AMINA = "Amina Distribution AS"

METER_DOMAIN_DSMR = "dsmr"
METER_DOMAIN_HOMEWIZARD = "homewizard"
METER_MANUFACTURER_AMSLESER = "amsleser.no"
METER_DOMAIN_TIBBER = "tibber"

SUPPORTED_METER_DEVICES = (
    (METER_DOMAIN_DSMR, None),
    (METER_DOMAIN_HOMEWIZARD, None),
    (METER_DOMAIN_TIBBER, None),
    (HA_INTEGRATION_DOMAIN_MQTT, METER_MANUFACTURER_AMSLESER),
)
SUPPORTED_METER_DEVICE_DOMAINS = [domain for (domain, _) in SUPPORTED_METER_DEVICES]


COORDINATOR_STATE_AWAITING_CHARGER = "awaiting_charger"
COORDINATOR_STATE_MONITORING_LOAD = "monitoring_loads"
COORDINATOR_STATES: tuple[str, ...] = (
    COORDINATOR_STATE_AWAITING_CHARGER,
    COORDINATOR_STATE_MONITORING_LOAD,
)

# Event constants
EVSE_LOAD_BALANCER_COORDINATOR_EVENT = f"{DOMAIN}_coordinator_event"
EVENT_ACTION_NEW_CHARGER_LIMITS = "new_charger_limits"
EVENT_ATTR_ACTION = "action"
EVENT_ATTR_NEW_LIMITS = "new_limits"


class Phase(Enum):
    """Enum for the phases."""

    L1 = "l1"
    L2 = "l2"
    L3 = "l3"


class OvercurrentMode(Enum):
    """Enum for overcurrent handling modes."""

    CONSERVATIVE = "conservative"
    OPTIMISED = "optimised"
