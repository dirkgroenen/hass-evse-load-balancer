---
name: create-integration
description: Create a new meter or charger integration for the EVSE Load Balancer
user-invocable: true
argument-hint: <meter|charger> <name> [--github-source <url>] [--non-interactive]
---

# Create Integration

Creates a new meter or charger integration with implementation, factory registration, and tests.

## Execution Modes

### Interactive Mode (default)
Prompts user for missing details. Used when called manually via `/create-integration`.

### Non-Interactive Mode (`--non-interactive`)
Auto-infers all parameters from upstream source code. Used in GitHub Actions workflows where no user interaction is possible.

**Behavior in non-interactive mode:**
- Never calls `AskUserQuestion`
- Fails immediately if critical parameters cannot be inferred
- Reports what was inferred vs assumed
- Returns structured failure state for workflow to handle

## Step 1: Parse Arguments

Extract from `$ARGUMENTS`:
- **type**: `meter` or `charger` (required)
- **name**: device name in snake_case (required)
- **--github-source**: URL to upstream HA integration source (optional, but required for non-interactive)
- **--non-interactive**: flag to enable non-interactive mode (optional)

**Failure handling:**
- If type/name missing:
  - Interactive: ask user
  - Non-interactive: **FAIL with message "MISSING_REQUIRED_ARGS: type and name required"**

## Step 2: Gather Details

### Interactive Mode:
Ask the user for the following. Present as a numbered list they can answer in one message:

**For both meters and chargers:**
1. Home Assistant integration domain (e.g., "shelly", "wallbox")
2. GitHub source URL of the upstream HA integration (e.g., `https://github.com/home-assistant/core/blob/dev/homeassistant/components/wallbox`)
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

### Non-Interactive Mode:
**Do NOT ask the user anything.** Instead, proceed directly to Step 3 to auto-infer parameters.

## Step 3: Fetch and Analyze Upstream Source

Use the provided GitHub URL to read the upstream integration's source code.

### For Meters:
Analyze sensor.py to extract:
- Entity keys or translation_keys for: active power, voltage, current (per phase L1/L2/L3)
- Check for: consumption/production sensors (net metering)
- Determine entity lookup strategy: unique_id suffix, translation_key, or exact unique_id

### For Chargers:
Analyze sensor.py, switch.py, number.py to extract:
- Status sensor: translation_key or unique_id pattern + all possible values
- Current limit sensor: translation_key or unique_id pattern
- Max current limit: check for max_current entity or assume typical hardware limit (32A)
- Set current limit service: analyze switch.py or number.py for service calls

**Non-Interactive Auto-Inference:**

Infer the following automatically from source code analysis:

1. **Domain**: Extract from GitHub URL path (e.g., `/components/wallbox/` → `wallbox`)

2. **Communication method**:
   - Check manifest.json for `mqtt` dependency → MQTT-based
   - Check for `zigbee2mqtt` or `Z2M` references → Zigbee2MQTT
   - Default: standard HA integration

3. **MQTT manufacturer**: If MQTT, search for `MANUFACTURER` constant or device info dict

4. **Entity lookup strategy**: Analyze unique_id generation:
   - If `f"{unique_id}_{sensor_type}"` → key suffix strategy
   - If uses `translation_key` field → translation_key strategy
   - If unique_id is complex → exact unique_id match

5. **Meters - sensor data format**:
   - Find "active_power" or "power" sensor → power+voltage
   - Find "current" sensor → direct current
   - Find both "consumption" and "production" → net metering

6. **Chargers - status values**: Extract all STATE_* constants or string literals used in status sensor

7. **Chargers - service call**: Search for service registration in switch.py or number.py, extract domain, service name, and service_data schema

8. **Chargers - per-phase support**: Default to False (single value) unless code shows per-phase arrays

**Failure Handling (Non-Interactive):**

If any critical parameter cannot be inferred:
- **FAIL with structured message**: `"INFERENCE_FAILED: Could not determine <parameter> from source code. Manual intervention required."`
- Do not proceed to Step 5
- Return immediately with failure state

If inference is uncertain but plausible:
- **Proceed with assumption**
- Document the assumption in Step 7 summary with "⚠️ ASSUMED:" prefix

## Step 4: Read Reference Implementations

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

### Interactive Mode Output:
- All files created/modified with paths
- Entity mappings used (so user can verify against their actual HA setup)
- Any assumptions made
- Reminder to test with actual hardware

### Non-Interactive Mode Output:

**On Success:**
```
STATUS: SUCCESS
TYPE: <meter|charger>
NAME: <name>
DOMAIN: <domain>
FILES_CREATED:
  - custom_components/evse_load_balancer/<type>s/<name>_<type>.py
  - tests/<type>s/test_<name>_<type>.py
FILES_MODIFIED:
  - custom_components/evse_load_balancer/const.py
  - custom_components/evse_load_balancer/<type>s/__init__.py
  - <additional files>

INFERRED_PARAMETERS:
  - domain: <value>
  - communication_method: <standard|mqtt|zigbee2mqtt>
  - entity_lookup_strategy: <key_suffix|translation_key|unique_id>
  - <additional inferred params>

ASSUMPTIONS:
  ⚠️ <any assumptions made with uncertain confidence>

NEXT_STEPS:
  - Run tests to verify implementation
  - Test with actual hardware
  - Verify entity mappings match your HA device
```

**On Failure:**
```
STATUS: FAILED
ERROR_CODE: <MISSING_REQUIRED_ARGS|INFERENCE_FAILED|VALIDATION_FAILED>
ERROR_MESSAGE: <detailed message>
MISSING_PARAMETERS: <list of parameters that couldn't be inferred>
MANUAL_ACTION_REQUIRED: <specific steps for human to complete>
```

Error codes:
- `MISSING_REQUIRED_ARGS`: Type or name not provided
- `INFERENCE_FAILED`: Could not infer critical parameters from source code
- `VALIDATION_FAILED`: Tests or linting failed after implementation
