"""Learned-state persistence: schema-versioned stores with flash-wear care.

``LearnedStateStores`` owns the two per-entry stores (MPC models, slow state
like the maintenance clock / rmot EMA / bias integrals) plus everything
hazardous about writing them: downgrade-safe loading, the rate limiter that
keeps continuously-drifting learned state from wearing out SD cards, and
deduplication against the last scheduled payload. What goes *into* the
payloads — and how a restored payload maps back onto runtime state — stays
with the coordinator; this module only moves bytes safely.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

from homeassistant.helpers.storage import Store

from .const import DOMAIN

try:
    from homeassistant.exceptions import UnsupportedStorageVersionError
except ImportError:
    # HA < 2026.3 has no downgrade signal: Store hands a newer-major payload
    # to ``_async_migrate_func`` instead, and our hook discards unknown
    # majors itself — so this fallback is never raised; it only keeps the
    # except clause in ``load`` valid on older installs.
    class UnsupportedStorageVersionError(Exception):  # type: ignore[no-redef]
        """Downgrade marker for Home Assistant releases before 2026.3."""


if TYPE_CHECKING:
    from collections.abc import Callable

    from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

STORE_VERSION = 1
# Debounce for delay-saves; batches a burst of changes into one write.
_SAVE_DELAY = 30.0
# Learned state (MPC history, rmot EMA, bias integrals) moves slowly but
# *continuously*, so saving "on change" degenerates to saving every cycle —
# one flash write per ~90 s, forever, on SD-card Home Assistant boxes. Persist
# at most every this many seconds instead; a crash loses only that much slow
# drift (clean stops still flush pending saves via the Store itself).
_PERSIST_INTERVAL = 900.0


class _LearnedStateStore(Store[dict[str, Any]]):
    """Learned-state store with explicit schema-migration semantics.

    Everything persisted here is re-learnable in hours, so the migration
    policy is deliberately blunt: a payload whose schema we don't positively
    recognise is discarded rather than risk a mis-read. Same-major minor
    drift reads forward-compatibly (loaders validate field-by-field anyway).
    """

    async def _async_migrate_func(
        self,
        old_major_version: int,
        _old_minor_version: int,
        old_data: dict[str, Any],
    ) -> dict[str, Any]:
        if old_major_version == STORE_VERSION:
            return old_data
        _LOGGER.warning(
            "climate_orchestrator: discarding persisted state with unknown"
            " schema v%s (current v%s); it will be re-learned",
            old_major_version,
            STORE_VERSION,
        )
        return {}


class LearnedStateStores:
    """The entry's two learned-state stores plus their write discipline."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry_id: str,
        *,
        mpc_payload: Callable[[], dict[str, Any]],
        state_payload: Callable[[], dict[str, Any]],
    ) -> None:
        """Create the stores; payload callables are the coordinator's views."""
        self._mpc_payload = mpc_payload
        self._state_payload = state_payload
        self._mpc_store: Store[dict[str, Any]] = _LearnedStateStore(
            hass, STORE_VERSION, f"{DOMAIN}.{entry_id}.mpc"
        )
        self._state_store: Store[dict[str, Any]] = _LearnedStateStore(
            hass, STORE_VERSION, f"{DOMAIN}.{entry_id}.maintenance"
        )
        # Flash-wear rate limiting: when a save was last scheduled, and the
        # payloads it was scheduled with (dedupe against no-op rewrites).
        self._last_persist: float | None = None
        self._mpc_scheduled: dict[str, Any] | None = None
        self._state_scheduled: dict[str, Any] | None = None

    async def load_mpc(self) -> dict[str, Any] | None:
        """Load the persisted MPC payload (None if absent or from the future)."""
        return await self._load(self._mpc_store, "MPC")

    async def load_state(self) -> dict[str, Any] | None:
        """Load the persisted slow-state payload (None if absent/future)."""
        return await self._load(self._state_store, "maintenance")

    @staticmethod
    async def _load(store: Store[dict[str, Any]], label: str) -> dict[str, Any] | None:
        """Load a store; a newer-schema payload never breaks setup.

        ``Store`` raises before our migrate hook when the stored *major*
        version exceeds the current one (downgrade scenario) — learned state
        is re-learnable, so discard it instead of failing the entry.
        """
        try:
            return await store.async_load()
        except UnsupportedStorageVersionError:
            _LOGGER.warning(
                "climate_orchestrator: persisted %s state was written by a"
                " newer release; discarding it (it will be re-learned)",
                label,
            )
            return None

    def maybe_persist(self) -> None:
        """Schedule learned-state saves, rate-limited for flash wear.

        Called every control cycle, but a store is only (delay-)saved when at
        least ``_PERSIST_INTERVAL`` has passed since the last scheduled save
        *and* its payload actually differs from what was last scheduled.
        """
        now = time.monotonic()
        if (
            self._last_persist is not None
            and now - self._last_persist < _PERSIST_INTERVAL
        ):
            return
        scheduled = False
        if (mpc := self._mpc_payload()) and mpc != self._mpc_scheduled:
            self._mpc_scheduled = mpc
            self._mpc_store.async_delay_save(self._mpc_payload, _SAVE_DELAY)
            scheduled = True
        if (state := self._state_payload()) != self._state_scheduled:
            self._state_scheduled = state
            self._state_store.async_delay_save(self._state_payload, _SAVE_DELAY)
            scheduled = True
        if scheduled:
            self._last_persist = now

    async def save_mpc_now(self) -> None:
        """Write the MPC payload immediately and sync the rate limiter."""
        payload = self._mpc_payload()
        await self._mpc_store.async_save(payload)
        self._mpc_scheduled = payload
        self._last_persist = time.monotonic()

    async def save_state_now(self) -> None:
        """Write the slow-state payload immediately and sync the rate limiter.

        Syncing matters: the payload is now on disk, so the next due cycle
        must not schedule a redundant write of the same bytes.
        """
        payload = self._state_payload()
        await self._state_store.async_save(payload)
        self._state_scheduled = payload
        self._last_persist = time.monotonic()


async def async_remove_stores(hass: HomeAssistant, entry_id: str) -> None:
    """Delete the entry's persisted stores (called on entry removal)."""
    for suffix in ("mpc", "maintenance"):
        store: Store[dict[str, Any]] = Store(
            hass, STORE_VERSION, f"{DOMAIN}.{entry_id}.{suffix}"
        )
        await store.async_remove()
