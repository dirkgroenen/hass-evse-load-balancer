"""
OCPP Charger implementation.

Integrates with the OCPP custom component (https://github.com/lbbrhzn/ocpp),
which exposes Home Assistant entities for any charger speaking OCPP 1.6 or
2.0.1.

Two control levers are supported and chosen at runtime:

* Session lever (ocpp >= 0.12):
  ``number.<cpid>_session_current_limit`` sends a ``TxProfile`` bound to
  the running transaction. Preferred: it is session-scoped, leaves the
  station ceiling to the user, and is the lever upstream recommends for
  dynamic control (the station slider may be persisted to charger flash).
* Station lever (any version):
  ``number.<cpid>_maximum_current`` sends a ``ChargePointMaxProfile``.
  Used when the session lever does not exist (ocpp < 0.12), when the
  charger keeps rejecting ``TxProfile``, or as a one-off safety fallback
  while the car is drawing current but no transaction is bound yet.

The charger applies ``min(station, session)``. When the station lever had
to be used as a fallback while the session lever is primary, the station
ceiling is restored to its configured maximum on the next successful
session write.

Unique-ids in the OCPP integration are dot-separated
(e.g. ``number.ocpp.<cpid>.maximum_current``), so the base ``HaDevice``
``_get_entity_id_by_key`` helper (which expects ``_<key>``) cannot be used.
This module provides a dot-aware lookup helper instead.
"""

import asyncio
import logging
from collections.abc import Coroutine
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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
    SessionCurrentLimit = "session_current_limit"  # ocpp >= 0.12

    # Switch entities
    ChargeControl = "charge_control"
    Availability = "availability"

    # Sensor entities (connector-level preferred, charger-level fallback)
    StatusConnector = "status_connector"
    Status = "status"
    TransactionId = "transaction_id"


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


class ControlLever(StrEnum):
    """Which OCPP number entity is used to steer the charger."""

    SESSION = "session_current_limit"
    STATION = "maximum_current"


# Hardware/profile defaults for OCPP chargers. The actual max current is
# read from the ``maximum_current`` number entity's ``max`` attribute.
OCPP_HW_MAX_CURRENT = 32
OCPP_HW_MIN_CURRENT = 0  # 0 == effectively paused via charging profile

# IEC 61851 defines 6A as the minimum charging current. Below this, most
# cars refuse to start, ignore the limit, or stop mid-session, so sub-6A
# requests are snapped to 0A (pause).
OCPP_CAR_MIN_CURRENT = 6

# How long to wait for a transaction to appear so a session limit can be
# bound to it (Preparing -> Charging, or after a transaction restart).
OCPP_SESSION_BIND_TIMEOUT = 60
# How long to give a raised session limit to lift SuspendedEVSE on its own
# before restarting the transaction.
OCPP_RESUME_GRACE = 15
# Consecutive session-limit rejections before the session lever is
# abandoned for this config entry (until reload).
OCPP_SESSION_MAX_FAILURES = 3
# Transaction restart: how long to wait for the new transaction id.
OCPP_NEW_TRANSACTION_TIMEOUT = 30

_POLL_INTERVAL = 1.0
_NO_TRANSACTION = (None, "", "0", "None", "unknown", STATE_UNAVAILABLE)


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

        # Entities of the parent device (``via_device``). On multi-connector
        # chargers running ocpp >= 0.12 the station-wide ``maximum_current``
        # lives on the charger device while status and session limit live
        # on the connector device the user selected.
        self._parent_entities: list[RegistryEntry] = []

        # Last value passed to ``set_current_limit`` BEFORE the IEC 61851
        # snap to 0A. Reported back by ``get_current_limit`` while we hold
        # the charger paused or are still binding a session limit, so the
        # balancer's manual-override detector does not mistake our own 0A
        # (or a not-yet-bound session) for user input.
        self._last_requested: dict[Phase, int] | None = None
        self._paused_by_us = False

        self._session_failures = 0
        self._session_disabled = False
        # True when the station ceiling was written as a fallback while the
        # session lever is primary; restored on the next session success.
        self._station_overridden = False
        self._task: asyncio.Task | None = None

        self.refresh_entities()

        _LOGGER.info(
            "OCPP charger '%s' wired up: lever=%s, session_current_limit=%s, "
            "maximum_current=%s, status_connector=%s, status=%s "
            "(entities on device: %d, on parent device: %d)",
            device_entry.name,
            self.control_lever,
            self._get_ocpp_entity_id(
                domain="number", key=OcppEntityMap.SessionCurrentLimit
            ),
            self._station_entity_id(),
            self._get_ocpp_entity_id(
                domain="sensor", key=OcppEntityMap.StatusConnector
            ),
            self._get_ocpp_entity_id(domain="sensor", key=OcppEntityMap.Status),
            len(list(self.entities)),
            len(self._parent_entities),
        )

    def refresh_entities(self) -> None:
        """Refresh entities of the device and of its parent device."""
        super().refresh_entities()
        parent_id = getattr(self.device_entry, "via_device_id", None)
        self._parent_entities = (
            list(self.entity_registry.entities.get_entries_for_device_id(parent_id))
            if parent_id
            else []
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
        next meter-value interval. A longer settle time avoids hammering
        the charger with rapid changes.
        """
        return 30

    @property
    def control_lever(self) -> ControlLever:
        """Return the lever currently used to steer the charger."""
        if self._session_entity_id() is not None:
            return ControlLever.SESSION
        return ControlLever.STATION

    async def async_setup(self) -> None:
        """Set up the charger."""

    async def async_unload(self) -> None:
        """Unload the OCPP charger."""
        self._cancel_task()

    def set_phase_mode(self, mode: PhaseMode, _phase: Phase | None = None) -> None:
        """
        Set the phase mode of the charger.

        OCPP 1.6 has no standardised single/three-phase switch (it is
        vendor-specific DataTransfer). The value is validated, switching is
        a no-op.
        """
        if mode not in PhaseMode:
            msg = "Invalid mode. Must be 'single' or 'multi'."
            raise ValueError(msg)
        # TODO(EVSE Load Balancer): Implement vendor-specific phase # noqa: FIX002
        # switching via OCPP DataTransfer when/if upstream support exists.
        # https://github.com/dirkgroenen/hass-evse-load-balancer/issues/9

    # ------------------------------------------------------------------ #
    # Writing the limit
    # ------------------------------------------------------------------ #

    async def set_current_limit(self, limit: dict[Phase, int]) -> None:
        """
        Set the current limit for the charger.

        OCPP applies one limit to all phases, so the lowest requested phase
        value is used. Requests in (0, 6) are snapped to 0A (pause); the
        charger then reports ``SuspendedEVSE``.

        Resume from ``SuspendedEVSE``:

        * station lever: push the new limit, then restart the transaction
          via ``charge_control`` (off -> on), because many firmwares do not
          re-energise the contactor on a profile replacement alone.
        * session lever: push the new limit within the same transaction and
          only restart the transaction if the charger is still suspended
          after ``OCPP_RESUME_GRACE`` seconds. The session limit is then
          re-bound to the new transaction.
        """
        self._cancel_task()

        value = min(limit.values())
        self._last_requested = dict(limit)

        if 0 < value < OCPP_CAR_MIN_CURRENT:
            _LOGGER.info(
                "Requested current %sA is below the %sA IEC 61851 minimum. "
                "Pausing charging (setting 0A) until headroom recovers.",
                value,
                OCPP_CAR_MIN_CURRENT,
            )
            value = 0

        value = max(OCPP_HW_MIN_CURRENT, min(value, OCPP_HW_MAX_CURRENT))
        self._paused_by_us = value == 0

        status = self._get_status()
        resuming = (
            status == OcppStatusMap.SuspendedEVSE and value >= OCPP_CAR_MIN_CURRENT
        )
        lever = self.control_lever

        _LOGGER.debug(
            "Setting OCPP current limit to %sA via %s (requested per-phase: %s, "
            "status=%s, resuming=%s)",
            value,
            lever,
            limit,
            status,
            resuming,
        )

        if lever is ControlLever.SESSION and await self._apply_session(
            value, status=status, resuming=resuming
        ):
            return
        await self._apply_station(value, resuming=resuming)

    async def _apply_session(
        self, value: int, *, status: str | None, resuming: bool
    ) -> bool:
        """
        Apply ``value`` via the session lever.

        Returns True when the request is handled (applied, or deferred until
        a transaction exists). Returns False when the caller must fall back
        to the station lever for this call.
        """
        session_id = self._session_entity_id()
        if session_id is None:
            return False

        if not self._entity_available(session_id):
            # No transaction is bound to the slider yet (Preparing, HA
            # restart, transaction restart in progress). Bind as soon as one
            # appears. If the car is already drawing current, enforce the
            # limit through the station ceiling meanwhile.
            self._schedule(self._bind_session_when_ready(value))
            if status == OcppStatusMap.Charging:
                _LOGGER.info(
                    "%s is unavailable while charging; enforcing %sA via the "
                    "station maximum until the session limit can be bound.",
                    session_id,
                    value,
                )
                return False
            _LOGGER.debug(
                "%s unavailable (no transaction yet); will bind %sA when the "
                "transaction starts.",
                session_id,
                value,
            )
            return True

        if await self._set_number(session_id, value):
            self._session_failures = 0
            await self._restore_station_ceiling()
            if resuming:
                self._schedule(self._verify_resume(value))
            return True

        self._register_session_failure()
        return False

    async def _apply_station(self, value: int, *, resuming: bool) -> None:
        """Apply ``value`` via the station-wide ``maximum_current`` lever."""
        station_id = self._station_entity_id()
        if station_id is None:
            _LOGGER.error(
                "Unable to set current limit: '%s' number entity not found "
                "for OCPP device %s",
                OcppEntityMap.MaximumCurrent,
                self.device_entry.name,
            )
            return

        # ``unknown`` is fine on ocpp >= 0.12 (no confirmed value yet);
        # ``unavailable`` means no SmartCharging or charger offline, and
        # a service call on it would be dropped silently.
        if not self._entity_available(station_id):
            _LOGGER.error(
                "Cannot set current limit: OCPP entity %s is unavailable. "
                "The charge point does not advertise the SmartCharging feature "
                "profile, or is offline.",
                station_id,
            )
            return

        if not await self._set_number(station_id, value):
            _LOGGER.error(
                "Charger rejected %sA on %s. Since ocpp 0.12 this slider no "
                "longer falls back to transaction profiles; chargers that "
                "reject a relative ChargePointMaxProfile need the integration's "
                "absolute-schedule option.",
                value,
                station_id,
            )
            return

        if self.control_lever is ControlLever.SESSION:
            self._station_overridden = True

        if resuming:
            await self._kick_charge_control()

    async def _restore_station_ceiling(self) -> None:
        """Lift a fallback station limit back to its configured maximum."""
        if not self._station_overridden:
            return
        station_id = self._station_entity_id()
        max_limit = self.get_max_current_limit()
        if station_id is None or max_limit is None:
            return
        ceiling = min(max_limit.values())
        if await self._set_number(station_id, ceiling):
            self._station_overridden = False
            _LOGGER.info(
                "Restored station ceiling %s to %sA; session limit is in control.",
                station_id,
                ceiling,
            )

    def _register_session_failure(self) -> None:
        self._session_failures += 1
        if self._session_failures >= OCPP_SESSION_MAX_FAILURES:
            self._session_disabled = True
            _LOGGER.warning(
                "Session Current Limit rejected %s times in a row for OCPP "
                "device %s; using the station-wide maximum_current until the "
                "integration is reloaded.",
                self._session_failures,
                self.device_entry.name,
            )

    async def _bind_session_when_ready(self, value: int) -> None:
        """Wait for a transaction and bind ``value`` to it as session limit."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + OCPP_SESSION_BIND_TIMEOUT
        while loop.time() < deadline:
            session_id = self._session_entity_id()
            if session_id is None:
                return
            if self._entity_available(session_id):
                if await self._set_number(session_id, value):
                    self._session_failures = 0
                    _LOGGER.info("Bound session limit %sA on %s", value, session_id)
                    await self._restore_station_ceiling()
                else:
                    self._register_session_failure()
                return
            await asyncio.sleep(_POLL_INTERVAL)
        _LOGGER.debug(
            "No transaction to bind a %sA session limit to within %ss",
            value,
            OCPP_SESSION_BIND_TIMEOUT,
        )

    async def _verify_resume(self, value: int) -> None:
        """Restart the transaction if a raised session limit did not resume."""
        await asyncio.sleep(OCPP_RESUME_GRACE)
        if self._get_status() != OcppStatusMap.SuspendedEVSE:
            _LOGGER.info(
                "Resumed from SuspendedEVSE on the session limit alone; "
                "no transaction restart needed."
            )
            return
        _LOGGER.info(
            "Still SuspendedEVSE %ss after raising the session limit to %sA; "
            "restarting the transaction.",
            OCPP_RESUME_GRACE,
            value,
        )
        previous = self._transaction_id()
        await self._kick_charge_control()
        await self._wait_for_new_transaction(previous)
        # The charger discarded the TxProfile with the old transaction.
        await self._bind_session_when_ready(value)

    async def _wait_for_new_transaction(self, previous: str | None) -> None:
        """Wait until the transaction id changes after a restart."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + OCPP_NEW_TRANSACTION_TIMEOUT
        while loop.time() < deadline:
            current = self._transaction_id()
            if current not in _NO_TRANSACTION and current != previous:
                return
            await asyncio.sleep(_POLL_INTERVAL)
        _LOGGER.warning(
            "No new OCPP transaction within %ss after restarting the transaction",
            OCPP_NEW_TRANSACTION_TIMEOUT,
        )

    async def _kick_charge_control(self) -> None:
        """
        Toggle charge_control off then on to force a transaction restart.

        The switch maps to RemoteStopTransaction / RemoteStartTransaction,
        which is what most chargers need to re-energise the contactor after
        ``SuspendedEVSE``.
        """
        switch_entity_id = self._get_ocpp_entity_id(
            domain="switch", key=OcppEntityMap.ChargeControl
        )
        if switch_entity_id is None:
            _LOGGER.warning(
                "Cannot kick charge_control: switch entity not found for OCPP "
                "device %s. The charger may remain in SuspendedEVSE until it is "
                "manually restarted.",
                self.device_entry.name,
            )
            return

        _LOGGER.info(
            "Kicking %s (off -> on) to resume charging from SuspendedEVSE",
            switch_entity_id,
        )
        for service in ("turn_off", "turn_on"):
            await self.hass.services.async_call(
                domain="switch",
                service=service,
                service_data={"entity_id": switch_entity_id},
                blocking=True,
            )

    async def _set_number(self, entity_id: str, value: int) -> bool:
        """Set an OCPP number entity; return False if the charger refused."""
        try:
            await self.hass.services.async_call(
                domain="number",
                service="set_value",
                service_data={"entity_id": entity_id, "value": value},
                blocking=True,
            )
        except (HomeAssistantError, TimeoutError) as err:
            _LOGGER.warning("Setting %s to %sA failed: %s", entity_id, value, err)
            return False
        return True

    # ------------------------------------------------------------------ #
    # Reading the limit
    # ------------------------------------------------------------------ #

    def get_current_limit(self) -> dict[Phase, int] | None:
        """
        Return the limit the charger currently applies.

        This is ``min(station, session)``; an unbound session limit
        (``unknown``/``unavailable``) does not count.

        While we hold the charger paused at 0A, or are still binding a
        session limit to a new transaction, the last requested value is
        reported instead. Otherwise the balancer's manual-override detector
        compares the real 0A (or the bare station ceiling) with its last
        applied value, concludes the user changed the limit, and adopts it,
        locking the charger at 0A.
        """
        station_id = self._station_entity_id()
        station = self._read_number(station_id)
        session = None
        session_id = self._session_entity_id()
        if session_id is not None and self._entity_available(session_id):
            session = self._read_number(session_id)

        values = [v for v in (station, session) if v is not None]
        effective = min(values) if values else None

        if self._last_requested is not None and (
            (self._paused_by_us and effective in (0, None)) or self._task_pending()
        ):
            return dict(self._last_requested)

        if effective is None:
            if station_id is None:
                _LOGGER.warning(
                    "Current limit not available. Make sure the OCPP '%s' "
                    "number entity is enabled.",
                    OcppEntityMap.MaximumCurrent,
                )
            return None
        return dict.fromkeys(Phase, effective)

    def get_max_current_limit(self) -> dict[Phase, int] | None:
        """
        Return the maximum configured current for the charger.

        Read from the ``max`` attribute of the ``maximum_current`` number
        entity (configured when adding the charge point), falling back to
        the OCPP hardware default.
        """
        station_id = self._station_entity_id()
        if station_id is None:
            _LOGGER.warning(
                "Max current limit not available - falling back to %sA. "
                "Make sure the OCPP '%s' number entity is enabled.",
                OCPP_HW_MAX_CURRENT,
                OcppEntityMap.MaximumCurrent,
            )
            return dict.fromkeys(Phase, OCPP_HW_MAX_CURRENT)

        attrs = self._get_entity_state_attrs(station_id) or {}
        max_value = attrs.get("max") or attrs.get("native_max_value")
        if max_value is None:
            return dict.fromkeys(Phase, OCPP_HW_MAX_CURRENT)
        return dict.fromkeys(Phase, int(float(max_value)))

    def has_synced_phase_limits(self) -> bool:
        """Return True: OCPP applies one limit to all phases."""
        return True

    def _get_status(self) -> str | None:
        """
        Return the current OCPP status.

        Prefers the connector-level ``status_connector`` sensor and falls
        back to the charge-point-level ``status`` sensor.
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
        return self._get_status() in [
            OcppStatusMap.Preparing,
            OcppStatusMap.Charging,
            OcppStatusMap.SuspendedEVSE,
            OcppStatusMap.SuspendedEV,
            OcppStatusMap.Finishing,
        ]

    def can_charge(self) -> bool:
        """See abstract Charger class for correct implementation of this method."""
        return self._get_status() in [
            OcppStatusMap.Preparing,
            OcppStatusMap.Charging,
            OcppStatusMap.SuspendedEVSE,
            OcppStatusMap.SuspendedEV,
        ]

    def is_charging(self) -> bool:
        """See abstract Charger class for correct implementation of this method."""
        return self._get_status() == OcppStatusMap.Charging

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _session_entity_id(self) -> str | None:
        if self._session_disabled:
            return None
        return self._get_ocpp_entity_id(
            domain="number", key=OcppEntityMap.SessionCurrentLimit
        )

    def _station_entity_id(self) -> str | None:
        return self._get_ocpp_entity_id(
            domain="number", key=OcppEntityMap.MaximumCurrent
        )

    def _transaction_id(self) -> str | None:
        entity_id = self._get_ocpp_entity_id(
            domain="sensor", key=OcppEntityMap.TransactionId
        )
        if entity_id is None:
            return None
        state = self._get_entity_state(entity_id)
        return None if state is None else str(state)

    def _entity_available(self, entity_id: str) -> bool:
        state = self.hass.states.get(entity_id)
        return state is not None and state.state != STATE_UNAVAILABLE

    def _read_number(self, entity_id: str | None) -> int | None:
        if entity_id is None:
            return None
        state = self._get_entity_state(entity_id, parser_fn=float)
        return None if state is None else int(state)

    def _schedule(self, coro: Coroutine[Any, Any, None]) -> None:
        self._cancel_task()
        self._task = self.hass.async_create_background_task(
            coro, name=f"evse_load_balancer_ocpp_{self.device_entry.id}"
        )

    def _cancel_task(self) -> None:
        if self._task is not None and not self._task.done():
            self._task.cancel()
        self._task = None

    def _task_pending(self) -> bool:
        return self._task is not None and not self._task.done()

    def _get_ocpp_entity_id(self, *, domain: str, key: str) -> str | None:
        """
        Find an OCPP-managed entity by its descriptor key.

        OCPP unique-ids are dot-separated
        (e.g. ``number.ocpp.<cpid>.maximum_current`` or
        ``ocpp.<cpid>.conn1.status_connector.sensor``). An exact match of
        ``key`` against one dot-separated part wins; a part ending in
        ``_<key>`` (e.g. ``connector_1_session_current_limit``) is the
        fallback. The selected device is searched before its parent.
        """
        pools = (list(self.entities), self._parent_entities)
        for exact in (True, False):
            for pool in pools:
                entity = next(
                    (
                        e
                        for e in pool
                        if e.domain == domain
                        and self._key_matches(e.unique_id, key, exact=exact)
                    ),
                    None,
                )
                if entity is not None:
                    if entity.disabled:
                        _LOGGER.error(
                            "Required entity %s is disabled. Please enable it!",
                            entity.entity_id,
                        )
                    return entity.entity_id
        _LOGGER.debug(
            "No OCPP entity found in domain=%s with key=%s for device %s",
            domain,
            key,
            self.device_entry.name,
        )
        return None

    @staticmethod
    def _key_matches(unique_id: str, key: str, *, exact: bool) -> bool:
        parts = unique_id.split(".")
        if exact:
            return key in parts
        return any(part.endswith(f"_{key}") for part in parts)
