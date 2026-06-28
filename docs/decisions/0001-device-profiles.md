# ADR-0001: Device profiles for hardware quirks

**Status:** Accepted
**Date:** 2026-06

## Context

Climate Orchestrator drives every managed device through a single
`ClimateAdapter` (`devices/adapter.py`) that assumes a well-behaved Home
Assistant `climate` entity: it reads the room temperature from the
`current_temperature` attribute, the setpoint from `temperature`, trusts the
reported `hvac_modes` / `min_temp` / `max_temp` / `target_temp_step`, and always
applies a command with the same two service calls (set mode, then set
temperature). TRV-specific behaviour — discovering the `valve_opening_degree`
and `local_temperature_calibration` number entities — lives in `devices/trv.py`
and is keyed off configurable *name hints* rather than per-model code.

That has been enough for the SONOFF TRVZB family this project targets. But real
thermostat hardware is full of quirks, and there is currently **nowhere to put
one**:

- **Read quirks** — a device that reports the room temperature under a
  non-standard attribute, or whose `hvac_action` is unreliable.
- **Capability quirks** — a device that misreports `hvac_modes`, or a wrong
  `min`/`max`/`step`.
- **Write quirks** — a device that needs the mode set *after* the temperature,
  a short settle delay between calls, a mode toggle to commit a calibration, or
  that silently rejects a setpoint write while off.
- **Discovery quirks** — a valve/calibration number named differently from the
  hint defaults.

Today the only way to express any of these is an `if manufacturer == …` branch
inside `ClimateAdapter` or the coordinator — exactly the kind of creeping
conditional the rest of the codebase has been careful to avoid. There is, in
fact, no device-model identification at all: nothing reads `manufacturer` /
`model` from the device registry.

## Decision

Introduce a single extensibility seam — a **`DeviceProfile`** value object,
resolved per entity by `(platform, manufacturer, model)` from the device
registry, that the `ClimateAdapter` consults for reading, capability detection,
and entity-name hints. Ship exactly one profile to start: a **generic** profile
that reproduces today's behaviour byte-for-byte, so the introduction of the seam
is provably behaviour-preserving (the existing device and snapshot tests are the
proof). Quirks then become small data (and, when genuinely needed, pure
functions) in a profile — never edits to the adapter or coordinator.

## Options Considered

### Option A: Status quo (per-device `if` branches as needed)

| Dimension        | Assessment                                       |
| ---------------- | ------------------------------------------------ |
| Complexity       | Low now, high later                              |
| Cost             | Zero upfront                                     |
| Scalability      | Poor — quirks tangle the adapter and coordinator |
| Team familiarity | High                                             |

**Pros:** nothing to build today.
**Cons:** every new device mutates shared, well-tested control code; no model
identification; conditionals accrete exactly where the codebase has kept them
out.

### Option B: `DeviceProfile` seam, generic-only, profiles added on demand (chosen)

| Dimension        | Assessment                                       |
| ---------------- | ------------------------------------------------ |
| Complexity       | Low–medium                                       |
| Cost             | One small module + adapter rewire                |
| Scalability      | Good — new hardware is additive (a new profile)  |
| Team familiarity | High (mirrors the existing collaborator pattern) |

**Pros:** behaviour-preserving introduction; quirks are isolated, typed, and
unit-testable; adding hardware never touches the coordinator; profiles are
plain value objects, consistent with the rest of the codebase.
**Cons:** a small indirection on every read/capability call; one more concept.

### Option C: Per-model registry with IO hooks, up front

| Dimension        | Assessment                |
| ---------------- | ------------------------- |
| Complexity       | High                      |
| Cost             | Large, mostly speculative |
| Scalability      | Excellent                 |
| Team familiarity | Medium                    |

**Pros:** maximally flexible; battle-tested shape.
**Cons:** builds machinery for devices we do not have; IO-in-hooks is harder to
test than the rest of this codebase; over-fit to a many-contributor project.

## Trade-off Analysis

The real choice is B vs C, and it turns on appetite. C's flexibility is only
worth its complexity with a stream of contributors adding cheap TRVs; this
project has one maintainer and one device family. B captures the *structural*
win of C — hardware support becomes additive instead of invasive — at a fraction
of the cost, and leaves a clean upgrade path: the write-strategy hook (B's
deferred Phase 4) is the same idea as C's `override_set_*`, but added the day a
device demands it, as a pure function. Choosing B now and growing into C's
surface later is strictly cheaper than building C speculatively.

## Consequences

- **Easier:** adding a device with a read/capability/discovery quirk is a new
  `DeviceProfile` plus a matcher entry — no change to the adapter or
  coordinator. Quirks are colocated and individually testable.
- **Easier:** the project now identifies hardware by manufacturer/model, opening
  the door to model-specific diagnostics and repairs later.
- **Harder:** one extra indirection to understand when reading the device layer
  (mitigated by the contributor guide and the generic profile being the obvious
  default).
- **To revisit:** when the first device needs a *write* quirk, add a pure
  write-strategy hook to `DeviceProfile` (ordered steps / pre-post mode toggle /
  settle delay) and route `ClimateAdapter.apply` through it. The seam is shaped
  for it; the machinery waits until then.

## Action Items

1. [x] Phase 1 — `devices/profiles.py`: `DeviceProfile` value object, the
   generic profile (today's read/capabilities/hints), and the resolver; route
   `ClimateAdapter` through it. Behaviour-preserving.
2. [x] Phase 2 — extract a concrete `SONOFF_TRVZB` profile matched by
   manufacturer/model; route the coordinator's valve/calibration hint
   resolution through the device's profile (global config hints stay as the
   fallback).
3. [x] Phase 3 — contributor guide: *Adding hardware support*.
4. [ ] Phase 4 (deferred) — pure write-strategy hook, added when a real device
   needs it.
