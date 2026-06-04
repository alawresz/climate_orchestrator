# Sensing and aggregation

Every control cycle starts from a sensor snapshot built by
`sensing/registry.py: build_snapshot`. This page covers how each managed
device's local readings are resolved, how the home-wide average is computed
(and optionally overridden), and how stale sensors are kept out of control.

## Area sensor resolution

Home Assistant lets each **area** declare its own temperature and humidity
sensor (Settings → Areas → *Related sensors*; stored on the area registry as
`temperature_entity_id` / `humidity_entity_id`). That is the source of truth,
rather than scanning entities by `device_class`:

1. For each managed climate device, resolve its **area** (device area, else
   entity area).
2. Read the area's **configured** temperature/humidity sensor from the area
   registry. That single entity *is* the area's local temperature/humidity — no
   guessing or averaging of arbitrary `sensor` entities.
3. If an area has **no configured sensor**, the device's local value **falls
   back to the home-wide average** — not to the device's own internal reading.
4. Sensors are re-resolved on area-registry updates, so changing an area's
   sensor in the UI takes effect without reconfiguring the integration.

## Home-wide average

The **home average** = mean across all temperature (and, separately, humidity)
sensors actually in use by the integration (i.e. the union of all matched area
sensors), recomputed each cycle. It is exposed as read-only `sensor` entities
(`sensor.climate_orchestrator_home_avg_temperature`,
`..._home_avg_humidity`) for visibility and automations.

Optionally area-weighted in a later phase; v1 uses a simple mean. The
aggregation helpers (mean-or-none, slope) are pure functions in
`sensing/aggregate.py`.

### User override

The config/options flow accepts optional whole-home average
temperature/humidity sensors (`home_temperature_sensor` /
`home_humidity_sensor`, e.g. covering rooms without managed devices). When set,
the override replaces the computed mean everywhere downstream — engine
home-side trigger, no-area-sensor fallback, AC bias room fallback, slope,
feels-like display.

The override is read through the same resolve path as every other sensor, so
the staleness guard applies; if it's unavailable, non-numeric, non-finite, or
stale, the *computed* mean stands in (keeping status/repairs truthful and
control alive).

!!! note "NaN/inf hardening"
    `nan`/`inf` parse as floats without raising, so every numeric read funnels
    through `util.as_float`, which rejects them.

### Provenance diagnostic

Each reading's provenance is carried on the snapshot
(`SmartClimateData.home_temp_source` / `home_humidity_source`:
`computed` / `external` / `fallback`) and surfaced by the `home_avg_source`
ENUM diagnostic sensor — `mixed` is the headline when the two readings differ,
with per-reading detail in the attributes.

## Sensor staleness guard

`build_snapshot` takes a `max_age_seconds` (from the `sensor_max_age` number,
minutes; default 360 = 6 h, `0` disables) and an injectable `now`. An area
sensor whose `last_reported` (falling back to `last_updated`) is older than the
max age is treated as **missing**:

- its value is dropped, so the home average and the device fall back exactly as
  for an offline sensor, and
- its id is collected into `SmartClimateData.stale_sensors`.

This stops a frozen-but-"available" sensor (a common Zigbee failure) from
silently driving control on a stale value. The set surfaces in diagnostics and
raises the `stale_sensor` repair. Measuring from `last_reported` (not
`last_changed`) means a legitimately stable temperature isn't mistaken for
stale.

Availability degradation more broadly — offline devices, the home average over
available sensors only, the `initializing`/`ok`/`degraded` status — is covered
in [Device control](device-control.md#availability-and-graceful-degradation).

Next: [Control model](control-model.md) — the band, the trigger law, and the
comfort index that consume these readings.
