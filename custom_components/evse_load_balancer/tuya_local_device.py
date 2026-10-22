"""Resolve known Tuya Local entities without depending on their display names."""

from math import isfinite

from homeassistant.helpers.device_registry import DeviceEntry

from .const import TUYA_LOCAL_DOMAIN
from .ha_device import HaDevice


def is_tuya_local_device(device: DeviceEntry, manufacturer: str, model: str) -> bool:
    """Match only the device profiles supported by these adapters."""
    return (
        any(domain == TUYA_LOCAL_DOMAIN for domain, _ in device.identifiers)
        and device.manufacturer == manufacturer
        and device.model == model
    )


def finite_number(value: object) -> float | None:
    """Reject unavailable, nonnumeric and nonfinite readings."""
    try:
        number = float(value)
    except (ValueError, TypeError):
        return None
    return number if isfinite(number) else None


class TuyaLocalDevice(HaDevice):
    """Look up Tuya Local's stable hyphen-separated entity config IDs."""

    def entity_id(self, config_id: str) -> str:
        """Resolve an enabled entity from the selected device's registry entries."""
        self.refresh_entities()
        matches = [
            entity
            for entity in self.entities
            if entity.platform == TUYA_LOCAL_DOMAIN
            and entity.unique_id.endswith(f"-{config_id}")
        ]
        if len(matches) != 1:
            msg = (
                f"Expected one Tuya Local entity for {config_id} "
                f"on {self.device_entry.name}"
            )
            raise ValueError(msg)
        entity = matches[0]
        if entity.disabled:
            msg = (
                f"Enable required entity {entity.entity_id} "
                "before configuring balancing"
            )
            raise ValueError(msg)
        return entity.entity_id

    def entity_attributes(self, config_id: str) -> dict | None:
        """Return current state attributes for a profile's entity."""
        return self._get_entity_state_attrs(self.entity_id(config_id))
