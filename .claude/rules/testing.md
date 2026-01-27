---
description: Test patterns and conventions
globs:
  - tests/**/*.py
---

# Testing Conventions

## Framework
- pytest with pytest-homeassistant-custom-component
- asyncio_mode = auto (configured in setup.cfg)

## File Location
- Meters: `tests/meters/test_<name>_meter.py`
- Chargers: `tests/chargers/test_<name>_charger.py`

## Standard Fixtures

```python
@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.services = MagicMock()
    hass.services.async_call = AsyncMock()  # chargers only
    return hass

@pytest.fixture
def mock_config_entry():
    return MockConfigEntry(
        domain="evse_load_balancer",
        title="<Name> Test",
        data={},
        unique_id="test_<name>",
    )

@pytest.fixture
def mock_device_entry():
    device = MagicMock(spec=DeviceEntry)
    device.id = "<domain>_123"
    device.identifiers = {("<domain>", "test_device")}
    return device
```

Instance fixtures: mock `refresh_entities` (patched in charger constructors since they call it in `__init__`), set `entities = []`, mock lookup methods as needed.

## Required Test Cases

### Meters
- `test_get_active_phase_current` - valid data per phase
- `test_get_active_phase_current_none` - missing sensor returns None
- `test_get_tracking_entities` - correct entities tracked, unrelated excluded
- `test_get_entity_map_for_phase_invalid` - invalid phase raises ValueError

### Chargers
- `test_is_charger_device` - device detection with correct/incorrect identifiers
- `test_set_current_limit` - verify service call args, uses `min(limit.values())`
- `test_get_current_limit` - entity state parsed to `dict[Phase, int]`
- `test_get_current_limit_missing` - returns None when entity unavailable
- `test_get_max_current_limit` + `_missing`
- `test_car_connected_true/false` - all valid connected + disconnected statuses
- `test_can_charge_true/false`
- `test_is_charging_true/false`

### Factory
- Update `tests/meters/test_meter_factory.py` when adding new meters
- Verify factory returns correct class for mock device with matching identifiers

## Patterns
- `assert result == {Phase.L1: X, Phase.L2: X, Phase.L3: X}` for phase dicts
- `assert result is None` for missing states
- Test all StatusMap values in status method tests
