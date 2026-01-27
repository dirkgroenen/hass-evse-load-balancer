---
name: review-integration
description: Review a meter or charger integration PR or file against project patterns and rules
user-invocable: true
argument-hint: <PR number or file path>
---

# Review Integration

Reviews a meter or charger integration for pattern compliance, correctness, and completeness.

## Step 1: Resolve Target

**If PR number** (e.g., `42`):
- Run `gh pr diff $ARGUMENTS` to get changed files
- Read all modified/added Python files in `meters/` or `chargers/`

**If file path** (e.g., `custom_components/evse_load_balancer/meters/shelly_meter.py`):
- Read the file directly
- Infer related files: test file, const.py changes, factory changes

## Step 2: Determine Type

From file paths, determine if this is a meter or charger. Read the implementation file(s).

## Step 3: Read Reference Files

Read for comparison:
- `custom_components/evse_load_balancer/const.py` (check registration)
- Relevant factory `__init__.py` (check registration)
- `custom_components/evse_load_balancer/config_flow.py` (check filter list for chargers)
- One existing implementation of the same type for pattern comparison
- The base class (`meters/meter.py` or `chargers/charger.py`)

## Step 4: Run Checklist

Evaluate each item. Mark as PASS, FAIL, or WARN with specific file:line references.

### Base Class Compliance
- [ ] Correct inheritance order (`Meter, HaDevice` or `HaDevice, Charger` or `Zigbee2Mqtt, Charger`)
- [ ] Both parent `__init__` called explicitly (not `super()`)
- [ ] `self.refresh_entities()` called at end of `__init__` (HaDevice-based only)
- [ ] All abstract methods implemented
- [ ] Correct return types

### Entity Lookup
- [ ] Entity map defined with phase keys using `cf.CONF_PHASE_KEY_*` constants
- [ ] Entity map covers all three phases (L1, L2, L3)
- [ ] Consistent lookup method (not mixing key/translation_key/unique_id)
- [ ] `_get_entity_map_for_phase` handles all phases + raises ValueError for invalid
- [ ] Comment with link to upstream HA integration source

### Error Handling
- [ ] None checks on all entity state reads
- [ ] `_LOGGER.warning()` for missing states (not errors, not silent)
- [ ] Error messages assigned to `msg` before raise
- [ ] No bare `raise Exception`
- [ ] Division by zero protected (voltage check before current calculation)

### Naming & Style
- [ ] File: `<name>_meter.py` or `<name>_charger.py`
- [ ] Class: `<Name>Meter` or `<Name>Charger`
- [ ] EntityMap/StatusMap follow naming convention
- [ ] Module docstring present
- [ ] `_LOGGER` defined at module level
- [ ] `# noqa: TID252` on parent package imports

### Charger-Specific
- [ ] `is_charger_device` is static, checks `device.identifiers`
- [ ] `set_current_limit` uses `min(limit.values())` for single-value chargers
- [ ] `set_current_limit` uses `blocking=True` on service calls
- [ ] Status hierarchy: `is_charging` subset of `can_charge` subset of `car_connected`
- [ ] `async_setup` and `async_unload` implemented

### Meter-Specific
- [ ] `get_active_phase_current` returns `int | None`
- [ ] `floor()` used when computing current from power/voltage
- [ ] Power units documented/converted correctly
- [ ] `get_tracking_entities` returns correct entity_ids

### Registration
- [ ] Domain constant in `const.py`
- [ ] Added to `SUPPORTED_METER_DEVICES` (meters) or `_charger_device_filter_list` (chargers)
- [ ] Factory updated with import + branch/list entry

### Tests
- [ ] Test file in `tests/meters/` or `tests/chargers/`
- [ ] Standard fixtures (mock_hass, mock_config_entry, mock_device_entry)
- [ ] All abstract methods tested
- [ ] Status methods tested with valid AND invalid states
- [ ] None/missing state paths tested
- [ ] Factory test updated (meters)

## Step 5: Automated Checks

```bash
ruff check <implementation_file>
pytest <test_file> -v 2>&1 || true
```

## Step 6: Output Review

Format as:

```
## Integration Review: <Name> <Meter|Charger>

### Summary
<1-2 sentence assessment>

### Results
| Category | Status | Details |
|----------|--------|---------|
| Base Class | PASS/FAIL | ... |
| Entity Lookup | PASS/FAIL | ... |
| Error Handling | PASS/FAIL | ... |
| Naming & Style | PASS/FAIL | ... |
| Type-Specific | PASS/FAIL | ... |
| Registration | PASS/FAIL | ... |
| Tests | PASS/FAIL | ... |

### Issues
1. **[FAIL] <category>**: <description>
   - File: <path>:<line>
   - Fix: <specific suggestion>

### Suggestions
- <optional improvements, not blocking>
```

If issues are found, offer to fix them directly or describe the fixes needed for `/create-integration` to apply.
