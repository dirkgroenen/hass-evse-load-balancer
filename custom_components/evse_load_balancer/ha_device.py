import logging
from typing import Any, Callable, Optional
from homeassistant.core import HomeAssistant
from homeassistant.helpers import (
    entity_registry as er,
)
from homeassistant.helpers.device_registry import (
    DeviceEntry,
)
from homeassistant.helpers.entity_registry import (
    RegistryEntry
)

_LOGGER = logging.getLogger(__name__)


class HaDevice():

    def __init__(
        self,
        hass: HomeAssistant,
        device_entry: DeviceEntry
    ):
        self.hass = hass
        self.device_entry = device_entry
        self.entity_registry = er.async_get(self.hass)

    def refresh_entities(self) -> None:
        """
        Refresh local list of entity maps for the meter.
        """
        self._entities = self._get_entities_for_device()

    def _get_entities_for_device(self):
        """
        Get all available entities for the linked HA device.
        """
        self.entities = self.entity_registry.entities.get_entries_for_device_id(
            self.device_entry.id,
            include_disabled_entities=True,
        )

    def _get_entity_id_by_translation_key(self, entity_translation_key: str) -> Optional[float]:
        """
        Get the entity ID for a given translation key.
        """
        entity: Optional[RegistryEntry] = next((e for e in self.entities if e.translation_key == entity_translation_key), None)
        if entity is None:
            raise ValueError(f"Entity not found for translation_key '{entity_translation_key}'")
        if entity.disabled:
            _LOGGER.error(f"Required entity {entity.entity_id} is disabled. Please enable it!")
        return entity.entity_id

    def _get_entity_state(self, entity_id: str, parser_fn: Callable = None) -> Optional[Any]:
        """
        Get the state of the entity for a given entity. Can be parsed
        """
        state = self.hass.states.get(entity_id)
        if state is None:
            _LOGGER.debug("State not found for entity %s", entity_id)
            return None

        try:
            return parser_fn(state.state) if parser_fn else state.state
        except ValueError:
            _LOGGER.warning("State for entity %s can't be parsed: %s", entity_id, state.state)
            return None

    def _get_entity_state_attrs(self, entity_id: str) -> Optional[dict]:
        """
        Get the state attributes for a given entity
        """
        state = self.hass.states.get(entity_id)
        if state is None:
            _LOGGER.debug("State not found for entity %s", entity_id)
            return None
        return state.attributes

    def _get_entity_state_by_translation_key(self, entity_translation_key: str, parser_fn: Callable = None) -> Optional[Any]:
        """
        Get the state of the entity for a given translation key.
        """
        entity_id = self._get_entity_id_by_translation_key(entity_translation_key)
        return self._get_entity_state(entity_id, parser_fn)

    def _get_entity_state_attrs_by_translation_key(self, entity_translation_key: str) -> Optional[dict]:
        """
        Get the state attributes for the entity for a given translation key.
        """
        entity_id = self._get_entity_id_by_translation_key(entity_translation_key)
        return self._get_entity_state_attrs(entity_id)
