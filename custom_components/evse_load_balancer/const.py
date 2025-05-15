"""Constants for the evse-load-balancer integration."""

from enum import Enum

DOMAIN = "evse_load_balancer"

CHARGER_DOMAIN_EASEE = "easee"
CHARGER_DOMAIN_ZAPTEC = "zaptec"

HA_INTEGRATION_DOMAIN_MQTT = "mqtt"
Z2M_DEVICE_IDENTIFIER_DOMAIN = "zigbee2mqtt" # Used by factory to verify Z2M origin from device.identifiers
MANUFACTURER_AMINA = "Amina Distribution AS"
MODEL_AMINA_S_OFFICIAL_NAME = "Amina S EV Charger" # From HA device info for Amina S
MODEL_AMINA_S_Z2M_INTERNAL = "amina S"         # Z2M's internal model ID for Amina S

SUPPORTED_CHARGER_DEVICE_DOMAINS = (
    CHARGER_DOMAIN_EASEE,
    CHARGER_DOMAIN_ZAPTEC,
    HA_INTEGRATION_DOMAIN_MQTT, # For config_flow to list devices from MQTT integration (like Amina)
)

POSSIBLE_CHARGER_EV_STATUSES = [
    "Not Connected",
    "EV Connected",
    "Ready to charge",
    "Charging",
    "Charging Paused",
    "EV Connected, Derated",
    "Ready to charge, Derated",
    "Charging, Derated",
    "Charging Paused, Derated",
    "unknown",
]

METER_DOMAIN_DSMR = "dsmr"
# If you add ESPHome meter support later, you'd add "esphome" here
SUPPORTED_METER_DEVICE_DOMAINS = (
    METER_DOMAIN_DSMR,
)


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

# --- Options Flow Constants ---
OPTION_CHARGE_LIMIT_HYSTERESIS = "charge_limit_hysteresis"
DEFAULT_OPTION_CHARGE_LIMIT_HYSTERESIS = 15

OPTION_MAX_FUSE_LOAD_AMPS = "max_fuse_load_amps"
DEFAULT_OPTION_MAX_FUSE_LOAD_AMPS = 0

# --- Main Config Flow Constants ---
CONF_FUSE_SIZE = "fuse_size"
CONF_PHASE_COUNT = "phase_count"
CONF_METER_DEVICE = "meter_device"
CONF_CHARGER_DEVICE = "charger_device"
CONF_CUSTOM_PHASE_CONFIG = "custom_phase_config"
CONF_PHASE_KEY_ONE = "l1"
CONF_PHASE_KEY_TWO = "l2"
CONF_PHASE_KEY_THREE = "l3"
CONF_PHASE_SENSOR_CONSUMPTION = "power_consumption"
CONF_PHASE_SENSOR_PRODUCTION = "power_production"
CONF_PHASE_SENSOR_VOLTAGE = "voltage"