# ADR-0003: Resolve room sensors from the Home Assistant area registry

**Status:** Accepted
**Date:** 2025-06 (retrospective)

## Context

A whole-home orchestrator needs, for each managed climate device, the *room's*
temperature and humidity — not the device's own internal sensor (a TRV's sensor
sits on the hot radiator). Something has to associate "this valve" with "that 
room sensor."

The obvious approach, and what most multi-device integrations do, is to make
the user enumerate the mapping in the config/options flow: pick a valve, pick
its temperature sensor, repeat. For a house full of TRVs that is a long, fragile
form that drifts out of date whenever the user renames or replaces a sensor.

Home Assistant already has the abstraction for "things in a room": **areas**,
and since HA 2025.2 an area carries a first-class `temperature_entity_id` and
`humidity_entity_id` (Settings → Areas → *Related sensors*).

## Decision

Do not ask the user to map sensors at all. Each managed device resolves to the
temperature/humidity sensor **configured on its Home Assistant area**
(`sensing/registry.py` reads `area.temperature_entity_id` /
`humidity_entity_id`); the home-wide average is taken over the distinct area
sensors actually in use. A device with no area, or an area with no sensor,
degrades gracefully (it falls back to the home average, and a repair notice
flags a total absence of any temperature source).

The cost of this choice is a hard floor: it requires **Home Assistant 2025.2**,
the release that added `area.temperature_entity_id`. That floor is recorded in
`hacs.json` (`"homeassistant": "2025.2.0"`) and guarded by the floor CI canary.

## Options Considered

### Option A: Explicit per-device sensor mapping in the config flow

**Pros:** no HA version floor; works on any HA.
**Cons:** long, fragile setup; duplicates information HA already models;
silently rots when entities are renamed/replaced.

### Option B: Area-registry resolution (chosen)

**Pros:** near-zero configuration; reuses the user's existing area setup; one
source of truth for "what's in this room"; renames/replacements are picked up
automatically; the home average falls out naturally.
**Cons:** requires HA 2025.2; a device must be assigned to an area, and the area
must have a related sensor (both surfaced via repairs/Status when missing).

## Consequences

- **Easier:** setup is "select your valves and ACs," nothing more; the mapping
  maintains itself.
- **Harder/constraint:** the project cannot support HA older than 2025.2, by
  design. Static import audits against older HA wheels are not enough — this is
  a *runtime attribute* floor, which is why the floor canary runs the suite
  against the pinned 2025.2 environment rather than just type-checking.
- **Related:** window/door detection resolves the same way (binary sensors in
  the device's area), entity- or device-level.
