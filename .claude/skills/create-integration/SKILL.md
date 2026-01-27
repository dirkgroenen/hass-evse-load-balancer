---
name: create-integration
description: Create a new meter or charger integration for the EVSE Load Balancer
user-invocable: true
argument-hint: <meter|charger> <name>
---

# Create Integration

Creates a new meter or charger integration with implementation, factory registration, and tests.

## Step 1: Parse Arguments

Extract `$ARGUMENTS` for type (meter/charger) and name (snake_case). If missing or ambiguous, ask the user.

## Step 2: Gather Details

Ask the user for the following. Present as a numbered list they can answer in one message:

**For both meters and chargers:**
1. Home Assistant integration domain (e.g., "shelly", "wallbox")
2. GitHub source URL of the upstream HA integration (e.g., `https://github.com/home-assistant/core/blob/dev/homeassistant/components/wallbox`). This is used to extract the exact entity keys/translation keys and is referenced in a code comment.
3. Communication method: standard HA integration (default) or MQTT/Zigbee2MQTT
4. If MQTT: manufacturer name as shown in HA device registry

**For meters:**
5. What sensor data is available per phase? Options:
   - Direct current reading (Amps)
   - Power (W or kW) + Voltage
   - Consumption power + Production power + Voltage (net metering)
6. Entity identifier format: provide the suffixes or translation keys for each phase sensor. Example for HomeWizard: `active_power_l1_w`, `active_voltage_l1_v`

**For chargers:**
5. Status entity identifier and all possible status values. Group them by:
   - Which mean "car connected"
   - Which mean "can charge" (ready to deliver power)
   - Which mean "is charging" (actively charging)
6. Current limit entity identifier (for reading current limit)
7. Max current limit entity identifier (or fixed hardware value in Amps)
8. How to set current limit: HA service domain + service name + service_data format. Example for Easee: `domain="easee", service="set_charger_dynamic_limit", service_data={"device_id": ..., "current": ...}`
9. Does the charger support per-phase current limits? (most don't - single value applied to all phases)

## Step 3: Fetch Upstream Source

Use the provided GitHub URL to read the upstream integration's sensor definitions. Extract the exact entity keys, translation keys, or unique_id patterns.

## Step 4: Read Reference

Read the closest existing implementation for reference:
- `custom_components/evse_load_balancer/meters/homewizard_meter.py` (key suffix, power+voltage)
- `custom_components/evse_load_balancer/meters/dsmr_meter.py` (translation_key, consumption+production)
- `custom_components/evse_load_balancer/meters/tibber_meter.py` (key suffix, direct current)
- `custom_components/evse_load_balancer/chargers/easee_charger.py` (HA services, translation_key)
- `custom_components/evse_load_balancer/chargers/lektrico_charger.py` (HA services, key suffix)
- `custom_components/evse_load_balancer/chargers/amina_charger.py` (MQTT/Z2M)

Also read:
- `custom_components/evse_load_balancer/const.py`
- The relevant factory `__init__.py`
- `custom_components/evse_load_balancer/config_flow.py`

## Step 5: Create Files

Create the implementation following `.claude/rules/integration-patterns.md`:
1. Implementation file: `custom_components/evse_load_balancer/<meters|chargers>/<name>_<meter|charger>.py`
2. Register: `const.py` domain constant + `SUPPORTED_METER_DEVICES` or filter list
3. Register: factory `__init__.py` import + branch/list entry
4. Register: `config_flow.py` `_charger_device_filter_list` (chargers only)
5. Tests: `tests/<meters|chargers>/test_<name>_<meter|charger>.py`
6. Factory test update: `tests/meters/test_meter_factory.py` (meters only)

## Step 6: Validate

Run linting and tests:
```bash
ruff check custom_components/evse_load_balancer/
pytest tests/<meters|chargers>/test_<name>_<meter|charger>.py -v
```

Fix any failures.

## Step 7: Summary

Output:
- All files created/modified with paths
- Entity mappings used (so user can verify against their actual HA setup)
- Any assumptions made
- Reminder to test with actual hardware
