# EVSE Load Balancer

Home Assistant custom component that dynamically load-balances EV chargers across available mains capacity. Extensible via Meters (power measurement sources) and Chargers.

## Commands

```bash
# Tests
pytest tests/
pytest tests/chargers/test_easee_charger.py   # single file
pytest --cov=custom_components tests/          # with coverage

# Lint (source only, excludes tests/ and sim/)
ruff check custom_components/
ruff check --fix custom_components/
ruff format custom_components/
```

## Architecture

### Core Loop (`coordinator.py`)
1-second interval: read phase current from `Meter` -> compute available capacity via `Balancer` -> allocate to chargers via `PowerAllocator` -> apply limits to `Charger`.

### Extension Points

**Meters** (`custom_components/evse_load_balancer/meters/`):
- ABC: `Meter` (`meter.py`) + utility mixin `HaDevice` (`ha_device.py`)
- Implement: `get_active_phase_current(phase) -> int | None`, `get_tracking_entities() -> list[str]`
- Registration: `const.py` domain + `SUPPORTED_METER_DEVICES`, `meters/__init__.py` factory branch
- Meter device filter in config_flow auto-generates from `SUPPORTED_METER_DEVICES`

**Chargers** (`custom_components/evse_load_balancer/chargers/`):
- ABC: `Charger` (`charger.py`) + utility mixin `HaDevice` (`ha_device.py`)
- Implement: `is_charger_device()`, `set_current_limit()`, `get_current_limit()`, `get_max_current_limit()`, `car_connected()`, `can_charge()`, `is_charging()`, `has_synced_phase_limits()`, `set_phase_mode()`, `async_setup()`, `async_unload()`
- Registration: `const.py` domain, `chargers/__init__.py` factory class list, `config_flow.py` `_charger_device_filter_list`

### Entity Lookup (`ha_device.py`)
Three strategies for resolving HA entities on a device:
- `_get_entity_id_by_key(suffix)` - unique_id ends with `_{suffix}` (HomeWizard, Tibber, Lektrico, AmsLeser)
- `_get_entity_id_by_translation_key(key)` - HA translation_key field (DSMR, Easee, Zaptec)
- `_get_entity_id_by_unique_id(uid)` - exact unique_id match (Keba)

### Phase Model
`Phase` enum: L1, L2, L3. All current limits are `dict[Phase, int]`.

### Key Files
- `const.py` - Domain constants, `SUPPORTED_METER_DEVICES`, `Phase`/`OvercurrentMode` enums
- `config_flow.py` - Device selector filters, config flow constants (`CONF_PHASE_*`)
- `ha_device.py` - Entity registry lookup utilities shared by all integrations
- `coordinator.py` - Main balancing loop
- `power_allocator.py` - Multi-charger allocation logic

## Conventions
- Python 3.13, ruff with ALL rules (see `.ruff.toml`)
- `msg = "..."; raise ValueError(msg)` - never inline strings in raise
- `# noqa: TID252` on parent package imports (`from ..const import ...`)
- `_LOGGER = logging.getLogger(__name__)` at module level after imports
- No magic strings: use constant classes (`EntityMap`, `StatusMap`) for HA entity identifiers
