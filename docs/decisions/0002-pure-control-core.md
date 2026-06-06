# ADR-0002: A pure, Home Assistant-free control core

**Status:** Accepted
**Date:** 2026-06 (retrospective)

## Context

The integration's value is in its *decisions*: comfort-curve math, hysteresis,
the saturating adaptive-comfort shift, the MPC thermal model and optimiser, the
setpoint-throttle and slope calculations. All of that is ordinary numerical
code, and all of it is easy to get subtly wrong (a flipped sign, a mis-scaled
`dt`, an off-by-one in a band edge) in ways that no type checker catches and
that integration tests only catch by luck.

Home Assistant code is, by contrast, awkward to test: it needs an event loop, a
`hass` instance, entity/area registries, and the `pytest-homeassistant-custom-
component` harness. If the decision math is interleaved with `hass.states.get`
calls and service calls, every test of the math pays the full HA setup cost and
the math can only be exercised through the seams HA exposes.

## Decision

Keep a hard architectural boundary: the **`control/` package and
`devices/model.py` import nothing from Home Assistant**. They operate on plain
values and dataclasses (`Band`, `DeviceDecision`, `DeviceCommand`,
`AdapterCapabilities`, …). All I/O — reading states, calling services,
registries, timers — lives in the coordinator, the entity platforms, and the
thin `devices/adapter.py`. The control core is a pure function of its inputs.

This makes two things possible that the project leans on heavily:

- **Mutation testing** (`mutmut`) targets `control/` alone, fast, with no HA
  harness — so the suite is measured on its ability to kill real math bugs.
- **Snapshot regression** pins the exact comfort-curve and adaptive-comfort
  outputs (`tests/unit/snapshots/`) as pure value-in/value-out checks.

## Options Considered

### Option A: Math inline in the coordinator/entities (chosen against)

**Pros:** fewer modules; no mapping layer between HA state and pure inputs.
**Cons:** every math test drags in the HA harness; mutation testing and pure
snapshots are impractical; the most bug-prone code is the least isolated.

### Option B: Pure control core, I/O at the edges (chosen)

**Pros:** the bug-prone code is the most testable; mutation testing and
snapshots become cheap and fast; the boundary doubles as documentation of what
is "decision" vs "plumbing."
**Cons:** a mapping layer (coordinator builds pure inputs from HA state, applies
pure outputs as service calls); a discipline to maintain.

## Consequences

- **Easier:** trustworthy tests of the math; refactors of HA plumbing can't
  silently change a decision, and vice versa.
- **Harder:** contributors must respect the boundary — no `homeassistant`
  import creeps into `control/`. (Enforceable later with an import-linter
  contract if it ever slips.)
- **Reinforced by** [ADR-0001](0001-device-profiles.md): device *behaviour*
  also moved to pure value objects, for the same testability reason.
