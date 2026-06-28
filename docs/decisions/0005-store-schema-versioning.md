# ADR-0005: Store schema versioning with downgrade-safe discard

**Status:** Accepted
**Date:** 2026-06 (retrospective)

## Context

The integration persists learned state across restarts: per-device MPC models,
the running-mean outdoor temperature, the self-tuning AC bias, latched demand,
and the maintenance clock (`persistence.py`, via HA's `Store`). That state
evolves as features land — a payload written by version *N* may not match what
version *N+1* expects, and a user who upgrades then rolls back (HACS makes this
easy) will have a *newer* payload on disk than the running code understands.

Mis-reading a stale or future payload is worse than having none: it can seed the
MPC model or bias integral with garbage and degrade control silently. But all of
this state is **re-learnable in hours** — none of it is precious.

## Decision

Version the stores (`STORE_VERSION`) and adopt a deliberately **blunt**
migration policy: a payload whose schema we don't positively recognise is
**discarded** (re-learned), never coerced.

- **Same-major, minor drift** reads forward-compatibly (loaders validate
  field-by-field anyway).
- **Unknown older major** → the migrate hook returns `{}` with a warning.
- **Newer major (downgrade)** → on HA ≥ 2026.3 `Store` raises
  `UnsupportedStorageVersionError` *before* any hook runs; we catch it and
  discard. On older HA there is no such signal, so `Store` routes the
  newer-major payload through the migrate hook, which discards it like any
  unknown major.

Because `UnsupportedStorageVersionError` only exists from HA 2026.3, its import
is guarded with a never-raised fallback class so the `except` clause stays valid
on the 2025.2 floor. No schema surprise can ever fail entry setup.

## Options Considered

| Option                                | Pros                                                     | Cons                                                                                                                      |
| ------------------------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| No versioning                         | Simplest                                                 | A changed payload shape silently mis-seeds control                                                                        |
| Versioned + write real migrations     | Preserves learned state across upgrades                  | Migration code to write and test for state that re-learns in hours — poor ROI, and can't help the *downgrade* case at all |
| Versioned + discard-on-doubt (chosen) | Setup never fails; no mis-reads; trivial to reason about | A schema change costs users a few hours of re-learning                                                                    |

## Consequences

- **Easier:** schema can evolve freely; a downgrade is safe; setup is robust to
  any stored garbage.
- **Cost:** a bumped `STORE_VERSION` discards learned state on first load after
  the change — acceptable given it re-learns quickly, and called out so it's a
  conscious choice when bumping.
- **Tested** across the matrix (same-major minor drift loads; unknown older
  major → empty; newer major → discarded, on both HA branches), with the
  downgrade path exercised by the floor canary.
