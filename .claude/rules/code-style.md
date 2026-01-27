---
description: Python and Home Assistant code conventions
globs:
  - custom_components/**/*.py
---

# Code Style

## Python
- Python 3.13, ruff ALL rules (see `.ruff.toml` for specific ignores)
- Max cyclomatic complexity: 25
- Type hints on all function signatures
- Union types: `X | None` (not `Optional[X]`)
- `dict.fromkeys(Phase, value)` for uniform phase dicts

## Structure
- Module docstring as first line (triple-quoted, single line)
- `_LOGGER = logging.getLogger(__name__)` after imports
- Constants (UPPER_SNAKE or class-based) before classes
- One primary class per file

## Error Handling
- Assign message to `msg` before raising: `msg = f"..."; raise ValueError(msg)`
- Never inline strings in `raise` statements

## Imports
- Parent package imports use `# noqa: TID252`: `from ..const import X  # noqa: TID252`
- Group: stdlib, third-party, HA, local
- `TYPE_CHECKING` guard for type-only imports

## Home Assistant
- Entity registry: `er.async_get(hass)`
- Device registry: `dr.async_get(hass)`
- Service calls: `await hass.services.async_call(domain=..., service=..., service_data=..., blocking=True)`
