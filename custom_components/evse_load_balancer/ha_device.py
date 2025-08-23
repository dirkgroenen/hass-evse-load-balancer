"""HA Device."""

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.helpers.device_registry import (
    DeviceEntry,
)

if TYPE_CHECKING:
    from homeassistant.helpers.entity_registry import RegistryEntry

_LOGGER = logging.getLogger(__name__)


class HaDevice:
    """Base class for HA devices."""

    def __init__(self, hass: HomeAssistant, device_entry: DeviceEntry) -> None:
        """Initialize the HaDevice instance."""
        self.hass = hass
        self.device_entry = device_entry
        self.entity_registry = er.async_get(self.hass)

    def refresh_entities(self) -> None:
        """Refresh local list of entity maps for the meter."""
        self._entities = self._get_entities_for_device()

    def _get_entities_for_device(self) -> None:
        """Get all available entities for the linked HA device."""
        self.entities = self.entity_registry.entities.get_entries_for_device_id(
            self.device_entry.id,
            include_disabled_entities=True,
        )

    def _get_entity_id_by_translation_key(self, entity_translation_key: str) -> str:
        """Get the entity ID for a given translation key."""
        entity: RegistryEntry | None = next(
            (e for e in self.entities if e.translation_key == entity_translation_key),
            None,
        )
        if entity is None:
            msg = f"Entity not found for translation_key '{entity_translation_key}'"
            raise ValueError(msg)
        if entity.disabled:
            _LOGGER.error(
                "Required entity %s is disabled. Please enable it!", entity.entity_id
            )
        return entity.entity_id

    def _get_entity_id_by_unique_id(self, entity_unique_id: str) -> str | None:
        """Get the entity ID for a given unique ID."""
        entity: RegistryEntry | None = next(
            (e for e in self.entities if e.unique_id == entity_unique_id),
            None,
        )
        if entity is None:
            msg = f"Entity not found for unique_id '{entity_unique_id}'"
            raise ValueError(msg)
        if entity.disabled:
            _LOGGER.error(
                "Required entity %s is disabled. Please enable it!", entity.entity_id
            )
        return entity.entity_id

    def _get_entity_id_by_key(self, entity_key: str) -> str | None:
        """
        Get the entity ID for a given key.

        Looks up the entity by checking all entities associated with the device
        whose unique_id end with the provided key.
        """
        entity: RegistryEntry | None = next(
            (e for e in self.entities if e.unique_id.endswith(f"_{entity_key}")),
            None,
        )
        if entity is None:
            msg = f"Entity with unique_id ending with '{entity_key}' not found"
            raise ValueError(msg)
        if entity.disabled:
            _LOGGER.error(
                "Required entity %s is disabled. Please enable it!", entity.entity_id
            )
        return entity.entity_id

    def _get_entity_state(
        self, entity_id: str, parser_fn: Callable | None = None
    ) -> Any | None:
        """Get the state of the entity for a given entity. Can be parsed."""
        state = self.hass.states.get(entity_id)
        if state is None:
            _LOGGER.debug("State not found for entity %s", entity_id)
            return None

        try:
            return parser_fn(state.state) if parser_fn else state.state
        except ValueError:
            _LOGGER.warning(
                "State for entity %s can't be parsed: %s", entity_id, state.state
            )
            return None

    def _get_entity_state_attrs(self, entity_id: str) -> dict | None:
        """Get the state attributes for a given entity."""
        state = self.hass.states.get(entity_id)
        if state is None:
            _LOGGER.debug("State not found for entity %s", entity_id)
            return None
        return state.attributes

    def _get_entity_state_by_translation_key(
        self, entity_translation_key: str, parser_fn: Callable | None = None
    ) -> Any | None:
        """Get the state of the entity for a given translation key."""
        entity_id = self._get_entity_id_by_translation_key(entity_translation_key)
        return self._get_entity_state(entity_id, parser_fn)

    def _get_entity_state_attrs_by_translation_key(
        self, entity_translation_key: str
    ) -> dict | None:
        """Get the state attributes for the entity for a given translation key."""
        entity_id = self._get_entity_id_by_translation_key(entity_translation_key)
        return self._get_entity_state_attrs(entity_id)

    def _get_entity_state_by_unique_id(
        self, entity_unique_id: str, parser_fn: Callable | None = None
    ) -> Any | None:
        """Get the state of the entity for a given unique ID."""
        entity_id = self._get_entity_id_by_unique_id(entity_unique_id)
        return self._get_entity_state(entity_id, parser_fn)

    def _get_entity_state_attrs_by_unique_id(
        self, entity_unique_id: str
    ) -> dict | None:
        """Get the state attributes for the entity for a given unique ID."""
        entity_id = self._get_entity_id_by_unique_id(entity_unique_id)
        return self._get_entity_state_attrs(entity_id)

    def _get_entity_state_by_key(
        self, entity_key: str, parser_fn: Callable | None = None
    ) -> Any | None:
        """Get the state of the entity for a given entity key."""
        entity_id = self._get_entity_id_by_key(entity_key)
        return self._get_entity_state(entity_id, parser_fn)

    def _get_entity_state_attrs_by_key(self, entity_key: str) -> dict | None:
        """Get the state attributes for the entity for a given entity key."""
        entity_id = self._get_entity_id_by_key(entity_key)
        return self._get_entity_state_attrs(entity_id)
