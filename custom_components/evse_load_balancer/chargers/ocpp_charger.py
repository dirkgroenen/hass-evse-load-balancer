"""
OCPP Charger implementation.

Integrates with the OCPP custom component
(https://github.com/lbbrhzn/ocpp) which provides Home Assistant entities
for any EV charger that supports the Open Charge Point Protocol
(1.6 / 2.0.1).

The integration exposes (per Charge Point / connector):
    - number.<cpid>_maximum_current   -> sets the per-phase current limit
    - switch.<cpid>_charge_control    -> starts/stops the transaction
    - sensor.<cpid>_status_connector  -> connector-level status
    - sensor.<cpid>_status            -> charge-point-level status

Unique-ids in the OCPP integration are composed using "." as separator
(e.g. ``number.ocpp.<cpid>.maximum_current``), so the base ``HaDevice``
``_get_entity_id_by_key`` helper (which expects ``_<key>``) cannot be
used directly. This module provides a small dot-aware lookup helper
instead.
"""

import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from ..const import CHARGER_DOMAIN_OCPP, Phase  # noqa: TID252
from ..ha_device import HaDevice  # noqa: TID252
from .charger import Charger, PhaseMode

if TYPE_CHECKING:
    from homeassistant.helpers.entity_registry import RegistryEntry

_LOGGER = logging.getLogger(__name__)


class OcppEntityMap:
    """
    Map OCPP entity keys (as defined by the OCPP integration).

    References
    ----------
    https://github.com/lbbrhzn/ocpp/blob/main/custom_components/ocpp/number.py
    https://github.com/lbbrhzn/ocpp/blob/main/custom_components/ocpp/switch.py
    https://github.com/lbbrhzn/ocpp/blob/main/custom_components/ocpp/sensor.py

    """

    # Number entities
    MaximumCurrent = "maximum_current"

    # Switch entities
    ChargeControl = "charge_control"
    Availability = "availability"

    # Sensor entities (connector-level preferred, charger-level fallback)
    StatusConnector = "status_connector"
    Status = "status"


class OcppStatusMap:
    """
    Map OCPP charger / connector statuses to their string representations.

    Values come from ``ChargePointStatus.<state>.value`` of the upstream
    ``ocpp`` python library and are exposed as-is by the OCPP integration.

    Reference
    ---------
    https://github.com/mobilityhouse/ocpp/blob/master/ocpp/v16/enums.py

    """

    Available = "Available"
    Preparing = "Preparing"
    Charging = "Charging"
    SuspendedEVSE = "SuspendedEVSE"
    SuspendedEV = "SuspendedEV"
    Finishing = "Finishing"
    Reserved = "Reserved"
    Unavailable = "Unavailable"
    Faulted = "Faulted"


# Hardware/profile defaults for OCPP chargers. The actual max current is
# read from the configured ``maximum_current`` number entity (which the
# user supplies during OCPP setup).
OCPP_HW_MAX_CURRENT = 32
OCPP_HW_MIN_CURRENT = 0  # 0 == effectively paused via charging profile

# IEC 61851 (the Mode 3 EV-charging signalling standard) defines 6A as the
# minimum charging current. Below this, most cars either refuse to start
# charging, ignore the limit entirely and pull more anyway, or stop
# mid-session. The OCPP integration faithfully transmits any value, so it
# is the charger backend's job to snap sub-6A requests to 0A (pause)
# rather than send a value the car will silently misbehave with.
OCPP_CAR_MIN_CURRENT = 6


class OcppCharger(HaDevice, Charger):
    """Implementation of the Charger class for OCPP-based chargers."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        device_entry: DeviceEntry,
    ) -> None:
        """Initialize the OCPP charger."""
        HaDevice.__init__(self, hass, device_entry)
        Charger.__init__(self, hass, config_entry, device_entry)
        self.refresh_entities()

        # Track the last value passed to ``set_current_limit`` (BEFORE
        # we snap it to 0 for IEC 61851 sub-minimum pauses). When the
        # charger is paused, ``get_current_limit`` reports this value
        # back so the balancer's manual-override detector does not see
        # the real OCPP slider (0A) and conclude that the user has
        # changed the ceiling to 0.
        self._last_requested: dict[Phase, int] | None = None

        # One-time discovery log so users (and bug reports) can see exactly
        # which OCPP entities the lookup helper picked.
        max_current_id = self._get_ocpp_entity_id(
            domain="number", key=OcppEntityMap.MaximumCurrent
        )
        status_conn_id = self._get_ocpp_entity_id(
            domain="sensor", key=OcppEntityMap.StatusConnector
        )
        status_id = self._get_ocpp_entity_id(domain="sensor", key=OcppEntityMap.Status)
        _LOGGER.info(
            "OCPP charger '%s' wired up: maximum_current=%s, "
            "status_connector=%s, status=%s (total entities on device: %d)",
            device_entry.name,
            max_current_id,
            status_conn_id,
            status_id,
            len(list(self.entities)),
        )

    @staticmethod
    def is_charger_device(device: DeviceEntry) -> bool:
        """
        Check if the given device is an OCPP charge point.

        OCPP devices register themselves with identifiers of the form
        ``(ocpp, <cpid>)`` or ``(ocpp, <cpid>-conn<N>)``.
        """
        return any(
            id_domain == CHARGER_DOMAIN_OCPP for id_domain, _ in device.identifiers
        )

    @property
    def current_change_settle_time(self) -> int:
        """
        Return the OCPP-specific settle time in seconds.

        OCPP chargers tend to confirm a new ChargingProfile only after the
        next meter-value interval (typically 30-60s). A slightly longer
        settle time avoids hammering the charger with rapid changes.
        """
        return 30

    async def async_setup(self) -> None:
        """Set up the charger."""

    def set_phase_mode(self, mode: PhaseMode, _phase: Phase | None = None) -> None:
        """
        Set the phase mode of the charger.

        OCPP 1.6 does not provide a standardised mechanism to switch
        between single- and three-phase charging - this depends on vendor
        specific DataTransfer messages. We accept the call (validate the
        value) but leave the actual switching as a no-op.
        """
        if mode not in PhaseMode:
            msg = "Invalid mode. Must be 'single' or 'multi'."
            raise ValueError(msg)
        # TODO(EVSE Load Balancer): Implement vendor-specific phase # noqa: FIX002
        # switching via OCPP DataTransfer when/if upstream support exists.
        # https://github.com/dirkgroenen/hass-evse-load-balancer/issues/9

    async def set_current_limit(self, limit: dict[Phase, int]) -> None:
        """
        Set the current limit for the charger.

        OCPP 1.6 only exposes a single ``maximum_current`` entity which is
        applied to all phases of the charge point (the OCPP integration
        sends a ChargingProfile with the requested amperage). We therefore
        use the lowest value across the requested phases.

        Below the IEC 61851 minimum of 6A, we send 0A (which the OCPP
        integration turns into a 0A ChargingProfile). Many chargers
        respond by transitioning to ``SuspendedEVSE`` -- the transaction
        is still alive, the car is just denied current. When budget
        recovers and we want to resume, we push the new (>=6A) limit
        AND force the charge_control switch to OFF then ON. The toggle
        is needed because some firmwares do not re-energise the
        contactor on a simple profile replacement; they wait for a
        fresh ``RemoteStartTransaction``. Skipping the toggle leaves
        the charger stuck in ``SuspendedEVSE`` indefinitely.
        """
        entity_id = self._get_ocpp_entity_id(
            domain="number", key=OcppEntityMap.MaximumCurrent
        )
        if entity_id is None:
            _LOGGER.error(
                "Unable to set current limit: '%s' number entity not found "
                "for OCPP device %s",
                OcppEntityMap.MaximumCurrent,
                self.device_entry.name,
            )
            return

        # OCPP exposes the ``maximum_current`` number entity as "unavailable"
        # when the charge-point does not advertise the SmartCharging feature
        # profile, or while it is offline. Calling ``number.set_value`` on an
        # unavailable entity is silently dropped, which produces exactly the
        # symptom of "no current change despite Load Balancer activity".
        # Surface this loudly so the user knows what to fix.
        entity_state = self.hass.states.get(entity_id)
        if entity_state is None or entity_state.state in ("unavailable", "unknown"):
            _LOGGER.error(
                "Cannot set current limit: OCPP entity %s is %s. "
                "This usually means the charge point does not advertise the "
                "SmartCharging feature profile, or is currently offline. "
                "Without SmartCharging the OCPP integration cannot push a "
                "ChargingProfile to the charger.",
                entity_id,
                entity_state.state if entity_state else "missing",
            )
            return

        value = min(limit.values())

        # Record what the balancer just asked for (BEFORE the snap).
        # ``get_current_limit`` will report this value back while the
        # charger is paused, so the manual-override detector sees the
        # same number it last applied -- not the post-snap 0A slider.
        self._last_requested = dict(limit)

        # Determine intent BEFORE we clamp, so we can tell apart
        # "balancer wants to pause" from "balancer wants to charge".
        requested_below_min = 0 < value < OCPP_CAR_MIN_CURRENT
        if requested_below_min:
            _LOGGER.info(
                "Requested current %sA is below the %sA IEC 61851 minimum. "
                "Pausing charging (setting 0A) until headroom recovers.",
                value,
                OCPP_CAR_MIN_CURRENT,
            )
            value = 0

        value = max(OCPP_HW_MIN_CURRENT, min(value, OCPP_HW_MAX_CURRENT))
        currently_paused = self._get_status() == OcppStatusMap.SuspendedEVSE
        resuming = currently_paused and value >= OCPP_CAR_MIN_CURRENT

        _LOGGER.debug(
            "Setting OCPP current limit on %s to %sA (requested per-phase: %s, "
            "status=%s, resuming=%s)",
            entity_id,
            value,
            limit,
            self._get_status(),
            resuming,
        )

        # Always push the new limit first so that on resume, the charger
        # sees the higher profile BEFORE the RemoteStart kicks in.
        await self.hass.services.async_call(
            domain="number",
            service="set_value",
            service_data={
                "entity_id": entity_id,
                "value": value,
            },
            blocking=True,
        )

        if resuming:
            # Force a transaction restart so the charger re-energises the
            # contactor. A simple profile replacement is not enough on
            # many OCPP-1.6 firmwares -- they remain in SuspendedEVSE
            # until they see a fresh RemoteStartTransaction.
            await self._kick_charge_control()

    async def _kick_charge_control(self) -> None:
        """
        Toggle charge_control off then on to force a transaction restart.

        Used to recover from ``SuspendedEVSE`` when raising the limit
        from 0A to >=6A. The switch maps to RemoteStopTransaction /
        RemoteStartTransaction, which is what most chargers actually
        need to re-energise the contactor.
        """
        switch_entity_id = self._get_ocpp_entity_id(
            domain="switch", key=OcppEntityMap.ChargeControl
        )
        if switch_entity_id is None:
            _LOGGER.warning(
                "Cannot kick charge_control: switch entity not found "
                "for OCPP device %s. The charger may remain in "
                "SuspendedEVSE until it is manually restarted.",
                self.device_entry.name,
            )
            return

        _LOGGER.info(
            "Kicking %s (off -> on) to resume charging from SuspendedEVSE",
            switch_entity_id,
        )
        await self.hass.services.async_call(
            domain="switch",
            service="turn_off",
            service_data={"entity_id": switch_entity_id},
            blocking=True,
        )
        await self.hass.services.async_call(
            domain="switch",
            service="turn_on",
            service_data={"entity_id": switch_entity_id},
            blocking=True,
        )

    def get_current_limit(self) -> dict[Phase, int] | None:
        """See base class for correct implementation of this method."""
        entity_id = self._get_ocpp_entity_id(
            domain="number", key=OcppEntityMap.MaximumCurrent
        )
        if entity_id is None:
            _LOGGER.warning(
                "Current limit not available. Make sure the OCPP "
                "'%s' number entity is enabled.",
                OcppEntityMap.MaximumCurrent,
            )
            return None

        state = self._get_entity_state(entity_id, parser_fn=float)
        if state is None:
            return None

        current = int(state)

        # IMPORTANT: when we have paused the charger by pushing 0A, the
        # OCPP slider sits at 0. The balancer's manual-override detector
        # compares the slider value against ``last_applied_current``
        # (which holds the value the allocator last asked for -- e.g.
        # 2A pre-snap). If we report 0, it concludes "the user moved
        # the slider to 0" and adopts 0 as the new ceiling, permanently
        # locking the charger at 0A.
        #
        # To prevent that, while the charger is in ``SuspendedEVSE`` we
        # report back the last value the balancer asked us for (which
        # ``last_applied_current`` was set to). The two stay in sync,
        # the override detector sees no change, and on the next
        # ``set_current_limit`` call we detect SuspendedEVSE and trigger
        # the resume kick. From the balancer's perspective the limit
        # tracks consistently; only ``set_current_limit`` translates the
        # value into the real OCPP profile (snap to 0 for sub-minimum,
        # kick switch on resume).
        if (
            current == 0
            and self._get_status() == OcppStatusMap.SuspendedEVSE
            and self._last_requested is not None
        ):
            return dict(self._last_requested)

        return dict.fromkeys(Phase, current)

    def get_max_current_limit(self) -> dict[Phase, int] | None:
        """
        Return maximum configured current for the charger.

        The OCPP integration models this via the ``native_max_value`` of
        the ``maximum_current`` number entity (configured by the user when
        adding the charge point). We read it from the state attributes,
        falling back to the OCPP hardware default if unavailable.
        """
        entity_id = self._get_ocpp_entity_id(
            domain="number", key=OcppEntityMap.MaximumCurrent
        )
        if entity_id is None:
            _LOGGER.warning(
                "Max current limit not available - falling back to %sA. "
                "Make sure the OCPP '%s' number entity is enabled.",
                OCPP_HW_MAX_CURRENT,
                OcppEntityMap.MaximumCurrent,
            )
            return dict.fromkeys(Phase, OCPP_HW_MAX_CURRENT)

        attrs = self._get_entity_state_attrs(entity_id) or {}
        max_value = attrs.get("max") or attrs.get("native_max_value")

        if max_value is None:
            return dict.fromkeys(Phase, OCPP_HW_MAX_CURRENT)
        return dict.fromkeys(Phase, int(float(max_value)))

    def has_synced_phase_limits(self) -> bool:
        """
        Return whether the charger has synced phase limits.

        OCPP exposes a single charge-point-wide ``maximum_current`` setting
        that applies equally across all phases, so limits are inherently
        synced.
        """
        return True

    def _get_status(self) -> str | None:
        """
        Return the current OCPP status.

        Prefers the connector-level ``status_connector`` sensor (which
        moves through Charging/Preparing/Finishing during a session) and
        falls back to the charge-point-level ``status`` sensor if the
        per-connector one is not present.
        """
        for key in (OcppEntityMap.StatusConnector, OcppEntityMap.Status):
            entity_id = self._get_ocpp_entity_id(domain="sensor", key=key)
            if entity_id is None:
                continue
            state = self._get_entity_state(entity_id)
            if state is not None:
                return state
        return None

    def car_connected(self) -> bool:
        """See abstract Charger class for correct implementation of this method."""
        status = self._get_status()
        return status in [
            OcppStatusMap.Preparing,
            OcppStatusMap.Charging,
            OcppStatusMap.SuspendedEVSE,
            OcppStatusMap.SuspendedEV,
            OcppStatusMap.Finishing,
        ]

    def can_charge(self) -> bool:
        """See abstract Charger class for correct implementation of this method."""
        status = self._get_status()
        return status in [
            OcppStatusMap.Preparing,
            OcppStatusMap.Charging,
            OcppStatusMap.SuspendedEVSE,
            OcppStatusMap.SuspendedEV,
        ]

    def is_charging(self) -> bool:
        """See abstract Charger class for correct implementation of this method."""
        return self._get_status() == OcppStatusMap.Charging

    async def async_unload(self) -> None:
        """Unload the OCPP charger."""

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _get_ocpp_entity_id(self, *, domain: str, key: str) -> str | None:
        """
        Find an OCPP-managed entity by its descriptor key.

        OCPP's unique_ids are dot-separated
        (e.g. ``number.ocpp.<cpid>.maximum_current`` or
        ``ocpp.<cpid>.conn1.status_connector.sensor``) so the standard
        ``_get_entity_id_by_key`` helper (which expects ``_<key>``) does
        not match. We match by HA domain and by checking that ``key`` is
        one of the dot-separated parts of the unique_id.
        """
        entity: RegistryEntry | None = next(
            (
                e
                for e in self.entities
                if e.domain == domain and key in e.unique_id.split(".")
            ),
            None,
        )
        if entity is None:
            _LOGGER.debug(
                "No OCPP entity found in domain=%s with key=%s for device %s",
                domain,
                key,
                self.device_entry.name,
            )
            return None

        if entity.disabled:
            _LOGGER.error(
                "Required entity %s is disabled. Please enable it!", entity.entity_id
            )
        return entity.entity_id
