"""Amina Charger implementation using direct MQTT communication."""
import json
import logging
from typing import Any

from homeassistant.components import mqtt
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant # State might not be used directly here
from homeassistant.core import callback as ha_core_callback
from homeassistant.helpers.device_registry import DeviceEntry

from ..const import Phase
from .charger import Charger, PhaseMode

_LOGGER = logging.getLogger(__name__)

# Zigbee2MQTT expose property names (keys in JSON payloads)
Z2M_PROPERTY_CHARGE_LIMIT = "charge_limit"
Z2M_PROPERTY_SINGLE_PHASE = "single_phase"
Z2M_PROPERTY_EV_CONNECTED = "ev_connected"
Z2M_PROPERTY_EV_STATUS = "ev_status"
Z2M_PROPERTY_CHARGING = "charging"

# Hardware limits for Amina S from Z2M documentation
AMINA_HW_MAX_CURRENT = 32  # Amps
AMINA_HW_MIN_CURRENT = 6   # Amps

# Base MQTT topics for Zigbee2MQTT
Z2M_BASE_TOPIC_ROOT = "zigbee2mqtt"


class AminaCharger(Charger):
    """Representation of an Amina S Charger using MQTT."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        device: DeviceEntry,
    ) -> None:
        """Initialize the Amina Charger instance."""
        super().__init__(hass, config_entry, device)
        
        self._z2m_friendly_name: str = device.name 
        _LOGGER.debug(f"AminaCharger: Initializing with Z2M friendly name: '{self._z2m_friendly_name}' from device.name") # ADDED LOG
        if not self._z2m_friendly_name:
            _LOGGER.error("AminaCharger: Z2M friendly name is empty or None!") # Ensure this is an error
            raise ValueError("Cannot initialize AminaCharger: Zigbee2MQTT friendly name is missing.")

        self._topic_state: str = f"{Z2M_BASE_TOPIC_ROOT}/{self._z2m_friendly_name}"
        self._topic_set: str = f"{self._topic_state}/set"
        self._topic_get_base: str = f"{self._topic_state}/get"

        self._mqtt_listeners: list[callable] = []
        self._state_cache: dict[str, Any] = {
            Z2M_PROPERTY_CHARGE_LIMIT: AMINA_HW_MIN_CURRENT,
            Z2M_PROPERTY_SINGLE_PHASE: False,
            Z2M_PROPERTY_EV_CONNECTED: False,
            Z2M_PROPERTY_EV_STATUS: "unknown",
            Z2M_PROPERTY_CHARGING: False,
        }
        self._is_mqtt_setup_done: bool = False

    async def async_setup_mqtt(self) -> None:
        """Subscribe to MQTT topics and request initial state. Called after __init__."""
        _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': Entered async_setup_mqtt. Current _is_mqtt_setup_done: {self._is_mqtt_setup_done}") # ADDED LOG
        if self._is_mqtt_setup_done:
            _LOGGER.warning(f"AminaCharger {self._z2m_friendly_name}: MQTT setup already performed.")
            return
        
        # Define message_received callback locally or as a class method
        # If it's a class method: self._message_received
        # For this example, keeping it local as in your original structure
        @ha_core_callback
        def message_received(msg) -> None:
            """Handle new MQTT messages from the device's state topic."""
            _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': MQTT RAW message received on {msg.topic}. Payload: {msg.payload}") # CHANGED TO INFO for visibility
            try:
                payload_json = json.loads(msg.payload)
                _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': Parsed payload: {payload_json}")
                
                for key, value in payload_json.items():
                    if key in self._state_cache: 
                        original_cached_value = self._state_cache.get(key)
                        processed_value = value 
                        if key in (Z2M_PROPERTY_SINGLE_PHASE, Z2M_PROPERTY_EV_CONNECTED, Z2M_PROPERTY_CHARGING):
                            if isinstance(value, str):
                                processed_value = value.lower() in ('true', 'on', 'enable')
                            else:
                                processed_value = bool(value)
                        
                        self._state_cache[key] = processed_value
                        if original_cached_value != processed_value:
                            _LOGGER.debug(f"AminaCharger {self._z2m_friendly_name}: Cache UPDATED for '{key}': from '{original_cached_value}' to '{processed_value}' (raw MQTT value: '{value}')") # CHANGED TO INFO
                        else:
                            _LOGGER.debug(f"AminaCharger {self._z2m_friendly_name}: Cache for '{key}' re-confirmed to '{processed_value}' (raw MQTT value: '{value}')")
                        
                        # Specifically log ev_status and ev_connected if found
                        if key == Z2M_PROPERTY_EV_STATUS:
                             _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': EV_STATUS found in payload and cached: '{processed_value}'")
                        if key == Z2M_PROPERTY_EV_CONNECTED:
                             _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': EV_CONNECTED found in payload and cached: '{processed_value}'")

            except json.JSONDecodeError:
                _LOGGER.error(f"AminaCharger {self._z2m_friendly_name}: Error decoding JSON from MQTT topic {msg.topic}: {msg.payload}", exc_info=True) # Added exc_info
            except Exception as e:
                _LOGGER.error(f"AminaCharger {self._z2m_friendly_name}: Error processing MQTT message from {msg.topic}: {e}", exc_info=True) # Added exc_info

        try:
            _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': Attempting to subscribe to {self._topic_state}")
            unsubscribe_state = await mqtt.async_subscribe(
                self.hass, self._topic_state, message_received, qos=0, encoding="utf-8"
            )
            self._mqtt_listeners.append(unsubscribe_state)
            _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': SUCCESSFULLY subscribed to MQTT topic '{self._topic_state}'")

            properties_to_get = [
                Z2M_PROPERTY_CHARGE_LIMIT, Z2M_PROPERTY_SINGLE_PHASE,
                Z2M_PROPERTY_EV_CONNECTED, Z2M_PROPERTY_EV_STATUS, Z2M_PROPERTY_CHARGING,
            ]
            all_gets_attempted_successfully = True # Assume success initially
            for prop in properties_to_get:
                get_topic = f"{self._topic_get_base}/{prop}"
                _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': Requesting initial state for '{prop}' on topic '{get_topic}'")
                try:
                    await mqtt.async_publish(self.hass, get_topic, payload="", qos=0, retain=False)
                except Exception as pub_e:
                    _LOGGER.error(f"AminaCharger '{self._z2m_friendly_name}': FAILED to publish GET for {prop} to {get_topic}: {pub_e}", exc_info=True) # Added exc_info
                    all_gets_attempted_successfully = False 
            
            if all_gets_attempted_successfully:
                self._is_mqtt_setup_done = True # Set only if sub and all GETs attempted (even if some GETs failed, sub is key)
                _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': MQTT subscription active and initial GETs published. MQTT setup considered complete.")
            else:
                # If GETs failed, subscription might still be active, but state incomplete.
                # Decide if this constitutes a failed setup. For now, if sub worked, let's try.
                # The earlier code set _is_mqtt_setup_done = True right after subscribe.
                # Let's stick to that for now, and log GET failures.
                # The crucial part is the subscription. GETs are for priming the cache.
                # If GETs fail, cache will populate when state message comes.
                self._is_mqtt_setup_done = True # Sticking to: if subscribe works, setup is "done" enough to listen
                _LOGGER.warning(f"AminaCharger '{self._z2m_friendly_name}': MQTT subscription succeeded, but one or more initial GET requests failed. Cache will update on next state publish.")


        except Exception as e:
            _LOGGER.error(f"AminaCharger '{self._z2m_friendly_name}': CRITICAL FAILURE during MQTT setup (e.g., subscription failed): {e}", exc_info=True) # Added exc_info
            self._is_mqtt_setup_done = False 
        
        _LOGGER.debug(f"AminaCharger {self._z2m_friendly_name}: Exiting async_setup_mqtt. Final _is_mqtt_setup_done state: {self._is_mqtt_setup_done}") # ADDED LOG


    async def async_unload_mqtt(self) -> None:
        """Unsubscribe from MQTT topics when the integration is unloaded."""
        _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': Entered async_unload_mqtt. Current _is_mqtt_setup_done: {self._is_mqtt_setup_done}") # ADDED LOG
        for unsubscribe in self._mqtt_listeners:
            try:
                unsubscribe()
            except Exception as e:
                _LOGGER.warning(f"AminaCharger '{self._z2m_friendly_name}': Error during MQTT unsubscribe: {e}")
        self._mqtt_listeners.clear()
        self._is_mqtt_setup_done = False
        _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': Exiting async_unload_mqtt. Final _is_mqtt_setup_done: {self._is_mqtt_setup_done}") # ADDED LOG

    def _publish_to_set_topic(self, payload_dict: dict[str, Any]) -> None:
        """Helper to publish a command to the Zigbee2MQTT /set topic from sync code."""
        payload_str = json.dumps(payload_dict)
        _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': Publishing to '{self._topic_set}': {payload_str}")
        self.hass.services.call(
            mqtt.DOMAIN,
            mqtt.SERVICE_PUBLISH,
            {
                mqtt.ATTR_TOPIC: self._topic_set,
                mqtt.ATTR_PAYLOAD: payload_str,
                mqtt.ATTR_QOS: 1,
                mqtt.ATTR_RETAIN: False,
            },
            blocking=False, 
        )

    async def _async_publish_to_set_topic(self, payload_dict: dict[str, Any]) -> None:
        """Async helper to publish a command to the Zigbee2MQTT /set topic."""
        payload_str = json.dumps(payload_dict)
        _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': Async publishing to '{self._topic_set}': {payload_str}")
        await mqtt.async_publish(
            self.hass, self._topic_set, payload_str, qos=1, retain=False
        )

    def set_phase_mode(self, mode: PhaseMode, phase: Phase) -> None:
        """Set the phase mode of the charger via MQTT."""
        _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': set_phase_mode called. Mode: {mode}. MQTT setup done: {self._is_mqtt_setup_done}") # ADDED LOG
        if not self._is_mqtt_setup_done:
            _LOGGER.warning(f"AminaCharger '{self._z2m_friendly_name}': MQTT not set up, cannot set phase mode.")
            return

        value_to_set: bool | None = None
        if mode == PhaseMode.SINGLE:
            value_to_set = True
        elif mode == PhaseMode.MULTI:
            value_to_set = False
        
        if value_to_set is not None:
            _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': Setting {Z2M_PROPERTY_SINGLE_PHASE} to {value_to_set} (Mode: {mode}) via MQTT.")
            self._publish_to_set_topic({Z2M_PROPERTY_SINGLE_PHASE: value_to_set})
        else:
            _LOGGER.warning(f"AminaCharger '{self._z2m_friendly_name}': Unknown PhaseMode for set_phase_mode: {mode}")

    async def set_current_limit(self, limit: dict[Phase, int]) -> None:
        """Set the charger limit in amps via MQTT."""
        _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': set_current_limit called. Limit: {limit}. MQTT setup done: {self._is_mqtt_setup_done}") # ADDED LOG
        if not self._is_mqtt_setup_done:
            _LOGGER.warning(f"AminaCharger '{self._z2m_friendly_name}': MQTT not set up, cannot set current limit.")
            return

        target_current = None
        if Phase.L1 in limit and limit[Phase.L1] is not None:
            target_current = limit[Phase.L1]
        elif limit: 
            for phase_val in limit.values():
                if phase_val is not None:
                    target_current = phase_val
                    break
        
        if target_current is None:
            _LOGGER.warning(f"AminaCharger '{self._z2m_friendly_name}': No valid current limit in {limit}")
            return

        clamped_current = max(AMINA_HW_MIN_CURRENT, min(AMINA_HW_MAX_CURRENT, int(target_current)))
        if clamped_current != int(target_current):
            _LOGGER.warning(
                f"AminaCharger '{self._z2m_friendly_name}': Requested current {target_current}A clamped to {clamped_current}A."
            )
        
        _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': Setting {Z2M_PROPERTY_CHARGE_LIMIT} to {clamped_current}A via MQTT.")
        await self._async_publish_to_set_topic({Z2M_PROPERTY_CHARGE_LIMIT: clamped_current})

    def get_current_limit(self) -> dict[Phase, int] | None:
        """Get the current charger limit in amps from internal cache."""
        # Warning for stale data is already inside based on _is_mqtt_setup_done
        current_limit_val = self._state_cache.get(Z2M_PROPERTY_CHARGE_LIMIT)
        is_single_phase = self._state_cache.get(Z2M_PROPERTY_SINGLE_PHASE, False)
        
        _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': get_current_limit called. MQTT setup done: {self._is_mqtt_setup_done}. Cached limit: {current_limit_val}, SinglePhase: {is_single_phase}") # ADDED LOG

        if not self._is_mqtt_setup_done: # Explicit check here for clarity before returning potentially stale/default data
            _LOGGER.warning(f"AminaCharger '{self._z2m_friendly_name}': MQTT not set up; get_current_limit from cache may be stale (limit: {current_limit_val}, single_phase: {is_single_phase}).")
            # Still proceed to return from cache as per original logic

        if current_limit_val is None:
            _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': {Z2M_PROPERTY_CHARGE_LIMIT} not in cache for get_current_limit.")
            return None
        
        try:
            current_limit_val = int(float(current_limit_val))
        except (ValueError, TypeError):
            _LOGGER.error(f"AminaCharger '{self._z2m_friendly_name}': Invalid {Z2M_PROPERTY_CHARGE_LIMIT} in cache: {current_limit_val}")
            return None

        if is_single_phase:
            return {Phase.L1: current_limit_val, Phase.L2: 0, Phase.L3: 0}
        else:
            return {
                Phase.L1: current_limit_val,
                Phase.L2: current_limit_val,
                Phase.L3: current_limit_val,
            }

    def get_max_current_limit(self) -> dict[Phase, int] | None:
        """Get the hardware maximum current limit of the charger."""
        max_val = AMINA_HW_MAX_CURRENT
        return { Phase.L1: max_val, Phase.L2: max_val, Phase.L3: max_val }

    def car_connected(self) -> bool:
        """Return whether the car is connected, from internal cache."""
        connected = bool(self._state_cache.get(Z2M_PROPERTY_EV_CONNECTED, False))
        _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': car_connected returning: {connected}. MQTT setup done: {self._is_mqtt_setup_done}. Cache value: {self._state_cache.get(Z2M_PROPERTY_EV_CONNECTED)}") # ADDED LOG
        if not self._is_mqtt_setup_done: # Warning if MQTT not ready
            _LOGGER.warning(f"AminaCharger '{self._z2m_friendly_name}': MQTT not set up; car_connected from cache may be stale.")
        return connected

    def can_charge(self) -> bool:
        """Return whether the car is connected and ready/accepting charge, from internal cache."""
        _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': can_charge called. MQTT setup done: {self._is_mqtt_setup_done}") # ADDED LOG
        if not self._is_mqtt_setup_done:
            _LOGGER.warning(f"AminaCharger '{self._z2m_friendly_name}': MQTT not set up; can_charge from cache may be stale.")

        car_is_connected = self.car_connected() # Uses the already logged car_connected method
        if not car_is_connected:
            _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': can_charge returning False because car is not connected.")
            return False

        ev_status = str(self._state_cache.get(Z2M_PROPERTY_EV_STATUS, "unknown")).lower()
        # Original debug log was fine, let's make it info for now for easier spotting
        _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': can_charge check -> ev_status from cache: '{ev_status}' (original case: '{self._state_cache.get(Z2M_PROPERTY_EV_STATUS)}')")
        
        # Using the Z2M converter logic for positive states
        is_chargeable_status = ev_status in ("charging", "ready_to_charge") 
        # Removed "resuming_charge" as it wasn't in Z2M converter logic
        _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': can_charge returning {is_chargeable_status} based on ev_status '{ev_status}'.")
        return is_chargeable_status
    
    def get_ev_status(self) -> str | None:
        """Get the raw EV status string from the internal cache."""
        current_status = self._state_cache.get(Z2M_PROPERTY_EV_STATUS)
        _LOGGER.debug(f"AminaCharger '{self._z2m_friendly_name}': get_ev_status returning: '{current_status}'. MQTT setup done: {self._is_mqtt_setup_done}") # ADDED LOG
        if not self._is_mqtt_setup_done:
            _LOGGER.warning(f"AminaCharger '{self._z2m_friendly_name}': MQTT not set up; get_ev_status from cache may be stale.")
        return current_status