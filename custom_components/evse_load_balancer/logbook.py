from collections.abc import Callable
from typing import Any

from homeassistant.components.logbook import (
    LOGBOOK_ENTRY_DOMAIN,
    LOGBOOK_ENTRY_MESSAGE,
    LOGBOOK_ENTRY_NAME,
)
from homeassistant.core import Event, HomeAssistant, callback

from .const import (
    DOMAIN,
    EVENT_ACTION_NEW_CHARGER_LIMITS,
    EVENT_ATTR_ACTION,
    EVENT_ATTR_NEW_LIMITS,
    EVSE_LOAD_BALANCER_COORDINATOR_EVENT,
    Phase
)


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, Any]]], None],
) -> None:
    """Describe EVSE events."""

    @callback
    def async_describe_charger_event(event: Event) -> dict[str, Any]:
        """Describe a charger change event."""
        data = event.data
        action = data.get(EVENT_ATTR_ACTION)

        if action == EVENT_ACTION_NEW_CHARGER_LIMITS:
            new_limits: dict[Phase, int] = data.get(EVENT_ATTR_NEW_LIMITS, {})
            message = ("charger limits set to: ",
                       ", ".join(f"{phase}: {limit}A" for phase, limit in new_limits.items())
                       )
        else:
            raise ValueError(f"Unknown action: {action}")

        return {
            LOGBOOK_ENTRY_NAME: "EVSE Load Balancer",
            LOGBOOK_ENTRY_MESSAGE: message,
            LOGBOOK_ENTRY_DOMAIN: DOMAIN,
        }

    async_describe_event(DOMAIN, EVSE_LOAD_BALANCER_COORDINATOR_EVENT, async_describe_charger_event)
