---
description: Rules for writing meter and charger integrations
globs:
  - custom_components/evse_load_balancer/meters/*.py
  - custom_components/evse_load_balancer/chargers/*.py
---

# Integration Patterns

## Meter Implementation

### Class Structure
- Inherit `Meter, HaDevice` (Meter first for MRO)
- Constructor: `(hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry)`
- Explicit parent init: `Meter.__init__(self, hass, config_entry)` then `HaDevice.__init__(self, hass, device_entry)`
- Call `self.refresh_entities()` at end of `__init__`

### Entity Map
- Module-level constant: `<NAME>_ENTITY_MAP: dict[str, dict[str, str]]`
- Keys: `cf.CONF_PHASE_KEY_ONE`, `cf.CONF_PHASE_KEY_TWO`, `cf.CONF_PHASE_KEY_THREE`
- Values: dict mapping sensor type constants (`cf.CONF_PHASE_SENSOR`, `cf.CONF_PHASE_SENSOR_VOLTAGE`, `cf.CONF_PHASE_SENSOR_CURRENT`, `cf.CONF_PHASE_SENSOR_CONSUMPTION`, `cf.CONF_PHASE_SENSOR_PRODUCTION`) to HA entity suffix/translation_key
- Include comment with link to upstream HA integration source (e.g. `@https://github.com/home-assistant/core/blob/dev/homeassistant/components/<name>/sensor.py`)

### Entity Lookup
Choose ONE strategy based on the upstream integration:
- **By key suffix** (most common): `_get_entity_id_by_key(suffix)` - unique_id ends with `_{suffix}`
- **By translation key**: `_get_entity_id_by_translation_key(key)` - uses HA translation_key
- **By unique_id**: `_get_entity_id_by_unique_id(uid)` - exact unique_id match

### Phase Mapping
Implement `_get_entity_map_for_phase(self, phase: Phase) -> dict`:
- if/if/if pattern: `if phase == Phase.L1: return ...[cf.CONF_PHASE_KEY_ONE]`
- End with `msg = f"Invalid phase: {phase}"; raise ValueError(msg)`

### get_active_phase_current
- Return type: `int | None`
- Direct current: read entity state, return `int(value)`
- Power + voltage: `floor((power_kW * 1000) / voltage)` or `floor(power_W / voltage)`
- Handle `None` with `_LOGGER.warning()` and return `None`

### get_tracking_entities
- Flatten entity map values, filter `self.entities` by matching keys
- Return `[e.entity_id for e in self.entities if any(e.unique_id.endswith(f"_{key}") for key in keys)]`

### Registration
1. `const.py`: Add `METER_DOMAIN_<NAME> = "<domain>"` (or `METER_MANUFACTURER_<NAME>` for MQTT)
2. `const.py`: Add tuple to `SUPPORTED_METER_DEVICES` - `(METER_DOMAIN_<NAME>, None)` or `(HA_INTEGRATION_DOMAIN_MQTT, METER_MANUFACTURER_<NAME>)`
3. `meters/__init__.py`: Import class + domain constant, add `if` branch in `meter_factory`
4. Config flow meter filter auto-generates from `SUPPORTED_METER_DEVICES` - no manual edit needed

---

## Charger Implementation

### Class Structure
- Inherit `HaDevice, Charger` (HaDevice first) - unless MQTT-based, then `Zigbee2Mqtt, Charger`
- Constructor: `(hass: HomeAssistant, config_entry: ConfigEntry, device_entry: DeviceEntry)`
- Explicit parent init: `HaDevice.__init__(self, hass, device_entry)` then `Charger.__init__(self, hass, config_entry, device_entry)`
- Call `self.refresh_entities()` at end of `__init__` (HaDevice-based only)

### Constant Classes
- `<Name>EntityMap` - Maps logical names to HA entity translation_keys/suffixes/keys
- `<Name>StatusMap` - Maps charger status strings to named constants
- Include docstring with link to upstream integration source

### is_charger_device (static)
```python
@staticmethod
def is_charger_device(device: DeviceEntry) -> bool:
    return any(id_domain == CHARGER_DOMAIN_<NAME> for id_domain, _ in device.identifiers)
```
For MQTT devices: also check `device.manufacturer`

### Status Methods Hierarchy
- `car_connected()`: car physically connected + authorized (broadest)
- `can_charge()`: connected + charger ready to deliver (subset of car_connected)
- `is_charging()`: actively drawing power (narrowest)
- Each reads via private `_get_status()` and compares against StatusMap constants

### set_current_limit
- Input: `dict[Phase, int]`
- Most chargers: `min(limit.values())` for single value
- Call: `await self.hass.services.async_call(domain=..., service=..., service_data=..., blocking=True)`
- MQTT chargers: publish via Zigbee2Mqtt helper

### get_current_limit / get_max_current_limit
- Return `dict[Phase, int] | None`
- Use `dict.fromkeys(Phase, int(state))` for uniform phase values
- Return `None` with `_LOGGER.warning()` when entity unavailable

### Registration
1. `const.py`: Add `CHARGER_DOMAIN_<NAME> = "<domain>"` (or manufacturer constant for MQTT)
2. `chargers/__init__.py`: Import class, add to class list in `charger_factory`
3. `config_flow.py`: Import domain constant, add entry to `_charger_device_filter_list`

---

## Common Patterns

### Error Handling
- `msg = "..."; raise ValueError(msg)` - never inline strings in raise
- `_LOGGER.warning()` for missing entity states, never raise on missing state
- `_LOGGER.debug()` for expected None states during startup

### Imports
```python
from ..const import CHARGER_DOMAIN_X, Phase  # noqa: TID252
from ..ha_device import HaDevice  # noqa: TID252
from .. import config_flow as cf  # noqa: TID252
```

### Naming
- File: `<name>_meter.py` / `<name>_charger.py`
- Class: `<Name>Meter` / `<Name>Charger`
- Entity map: `<NAME>_ENTITY_MAP` (meters) or `<Name>EntityMap` class (chargers)
- Status map: `<Name>StatusMap` class (chargers only)
- Module docstring: `"""<Name> Meter implementation."""` / `"""<Name> Charger implementation."""`
