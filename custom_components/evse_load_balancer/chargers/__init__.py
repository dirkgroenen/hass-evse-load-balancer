"""EVSE Load Balancer Chargers."""

from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr

from .amina_charger import AminaCharger
from .charger import Charger
from .easee_charger import EaseeCharger
from .keba_charger import KebaCharger
from .lektrico_charger import LektricoCharger
from .wallbox_charger import WallboxCharger
from .zaptec_charger import ZaptecCharger

if TYPE_CHECKING:
    from homeassistant.helpers.device_registry import DeviceEntry


async def charger_factory(
    hass: HomeAssistant, config_entry: ConfigEntry, device_entry_id: str
) -> Charger:
    """Create a charger instance based on the device's properties."""
    registry = dr.async_get(hass)
    device: DeviceEntry | None = registry.async_get(device_entry_id)

    if not device:
        msg = f"Device with ID {device_entry_id} not found in registry."
        raise ValueError(msg)

    for charger_cls in [
        AminaCharger,
        EaseeCharger,
        ZaptecCharger,
        KebaCharger,
        LektricoCharger,
        WallboxCharger,
    ]:
        if charger_cls.is_charger_device(device):
            return charger_cls(hass, config_entry, device)

    msg = f"Unsupported device: {device.name} (ID: {device_entry_id}). "
    raise ValueError(msg)
