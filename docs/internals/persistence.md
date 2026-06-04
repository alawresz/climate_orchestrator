# Persistence and restore

Learned and latched state survives restarts; transient counters deliberately do
not. Persistence is coordinator-owned, schema-versioned, flash-wear-aware, and
bounded.

## Stores and what they hold

A coordinator-owned `Store` (versioned) holds:

- learned MPC parameters/observer state per device,
- preset values,
- latched demand/hysteresis state, and
- the self-tuning AC bias.

All of it is restored on startup with safe priors. Beyond the store, every
tunable persists via `RestoreNumber`/`RestoreEntity` and re-runs control on
change, and the whole-home `climate` entity restores its mode, preset, and
manual band across restarts (`RestoreEntity`) — a restart no longer silently
turns the system off.

What is *not* persisted: the rolling runtime/cycle samples behind the
per-device runtime and cycles-per-hour diagnostics are transient and reset on
restart, and the per-AC adaptive-bias accumulator's in-memory component
re-learns in minutes.

## Schema versioning

The store subclass `_LearnedStateStore` (`coordinator.py`) carries explicit
schema-migration semantics. Everything persisted is re-learnable in hours, so
the migration policy is deliberately blunt: a payload whose schema we don't
positively recognise is discarded rather than risk a mis-read.

- **Same-major minor drift** reads forward-compatibly (loaders validate
  field-by-field anyway).
- **An unknown older major** is discarded by the migrate hook
  (`_async_migrate_func` returns `{}` with a warning).
- **A newer major** — the downgrade case, where `Store` raises before any hook
  runs — is caught and discarded too.

Learned state is always re-learnable, so no schema surprise can fail setup.

## Flash-wear rate limiting

Learned state (MPC history, the running-mean-outdoor EMA, bias integrals) moves
continuously, so per-cycle delay-saves would mean a write every ~90 s forever
on SD-card boxes. Instead, `_maybe_persist()` schedules a save at most every
`_PERSIST_INTERVAL` (15 min) and only when the payload actually changed.
Unload/shutdown flushes whatever the limiter was holding back.

## Background-task lifecycle

Fire-and-forget work (debounced refreshes, store saves, auto valve maintenance)
is spawned exclusively via the coordinator's `_background()` helper —
`ConfigEntry.async_create_background_task` — so every task is tracked by the
entry and cancelled on unload; nothing outlives the coordinator.

## Restore semantics and bounded runtime state

Restored payloads are validated before use (see the
[MPC numerical hardening summary](mpc.md#numerical-hardening-summary) for the
per-controller checks), and runtime state is bounded:

- **Store eviction of unmanaged entities:** store restore filters to
  currently-managed entities — a removed device's keys would otherwise cycle
  store→runtime→store forever.
- **Window-timer pruning:** per-area window timers are pruned each cycle
  against the live snapshot.
- **Forecast cap:** the hourly forecast cache is capped
  (`_FORECAST_MAX_HOURS`).
- **Slope samples:** the slope sample deque has a hard `maxlen`.

Next: [Testing](../project/testing.md) — how all of this is verified.
