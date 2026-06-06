# Device control strategies

The control engine decides *whether* each device should heat or cool; this page
covers *how* that intent becomes commands, which differs for radiator valves
and air conditioners.

## The adapter

A single `ClimateAdapter` (`devices/adapter.py`) decouples control from
integration specifics — it drives *any* HA `climate` entity through the standard
services and carries no per-vendor logic itself:

```python
class ClimateAdapter:
    def __init__(self, hass, entity_id, profile: DeviceProfile | None = None): ...
    def read(self) -> DeviceState: ...
    def capabilities(self) -> AdapterCapabilities: ...
    async def apply(self, command: DeviceCommand) -> None: ...
```

There are no per-vendor adapter subclasses; hardware variation is expressed as
*data* in a `DeviceProfile` the adapter reads through (see below).

**Hardware portability.** A single `ClimateAdapter`
(`devices/adapter.py`) drives *any* HA `climate` entity (TRV or AC):
`can_heat/can_cool/can_dry`, `min_temp`/`max_temp`/`target_step` are all read
from the device's own reported attributes, so adding a different AC or a
standard TRV needs no code change. The only hardware-coupled assumption is
*discovering a TRV's `valve_opening_degree` / `local_temperature_calibration`
`number` entities* for `mpc`/`offset` modes, done by name-matching
(`find_related_number` in `devices/trv.py`). Those name hints default to
Zigbee2MQTT/SONOFF naming but are **user-configurable** in the options flow
(`valve_opening_hints` / `calibration_hints`, comma-separated; parsed to a
lower-cased tuple by the coordinator), so another brand's naming can be
supported without code changes. `target` mode (the default) needs none of this.

**Device profiles.** Beyond user-configurable hints, per-model quirks (a
non-standard temperature attribute, a misreported capability, vendor-specific
number names) live in a `DeviceProfile` (`devices/profiles.py`), resolved per
entity from the device registry by `(integration, manufacturer, model)`. The
`ClimateAdapter` reads through the resolved profile; the generic profile is the
standard contract above. To add hardware support, see
[Adding hardware support](../project/adding-hardware.md) and
[ADR-0001](../decisions/0001-device-profiles.md).

## TRV controller (mpc, offset, target)

The `calibration_mode` select chooses the strategy: `target` (mode + setpoint,
default), `mpc` (drive valve via MPC), `offset` (bias local temperature).

- **Primary (`mpc`):** Model Predictive Control computing a **valve opening %**
  (the TRVZB accepts it directly) — see [MPC](mpc.md). When the device is not
  heating (idle/off/window/gated), the valve is explicitly driven to **0%**
  rather than left at its last commanded opening — otherwise a TRV can linger
  open and keep heating (a recurring failure mode in comparable integrations).

    !!! warning "Hardware-unvalidated"
        `valve_opening_degree` semantics are firmware-dependent on the TRVZB,
        so MPC remains hardware-unvalidated; `target` is the safe default.

- **Secondary/fallback (`offset`):** `local_temperature_calibration` offset —
  feed the TRV a biased local temperature (true measured − external truth) so
  its internal loop keeps the valve open until the *room* reaches target. Used
  when valve control is unavailable or as a complement.
- **Forecast preconditioning** (opt-in, MPC mode only) feeds the weather
  entity's hourly forecast into the valve optimisation so a radiator pre-heats
  ahead of a cold spell, and can only ever *raise* the valve — see
  [MPC: forecast preconditioning](mpc.md#forecast-preconditioning).
- A TRV in `mpc`/`offset` mode with no discoverable valve/calibration number
  falls back to `target` and raises a repair.

## AC controller — setpoint bias + offset

A Midea-class AC has no sensor-offset lever, so the equivalent trick is
**setpoint biasing**:

- To keep cooling until the *room* (external sensor) hits target, command the
  AC a setpoint **below** the cool target by a bias, so the AC's own indoor
  sensor doesn't prematurely satisfy.
- **Self-tuning AC bias (default on, `self_tuning_ac_bias`):** integral
  feedback (`control/adaptive_bias.py`). While the AC is actively cooling and
  the room is above target, an accumulator integrates `Ki · error · dt` and
  adds to the manual base bias; when not cooling it decays. Anti-windup clamps
  the add-on to `[0, max − base]`. The manual `ac_setpoint_bias` is the floor;
  `ac_setpoint_bias_max` is the ceiling. This auto-tunes the steady-state
  offset a fixed bias only approximates and removes manual tuning. The per-AC
  accumulator lives in coordinator state (in-memory; re-learns in minutes after
  a restart).
- **Compressor anchoring (proportional):** an AC only runs its compressor when
  the commanded setpoint is below what *its own* internal sensor reads —
  otherwise it idles/fans. Whenever cooling is wanted, `build_command` anchors
  the setpoint to the AC's reported temperature, pushed down by
  `max(room_above_target, AC_COOL_KICK)` where
  `room_above_target = room_eff − cool_target`. The depth scales with how far
  the room is above target: a room 3 °C over target drives the AC ~3 °C below
  its own reading (cool hard), while a room just over target gets the
  `AC_COOL_KICK` (1 °C) floor (enough to keep the compressor on). The final
  setpoint is `min(cool_target − bias, internal − drive)` — the room-sensor
  calc still caps it. The room sensor (via the engine releasing the demand)
  ends the call. This is the AC equivalent of the TRV offset/MPC trick, and is
  why the fixed bias alone wasn't enough when the AC's own sensor sat below the
  room.
- Every commanded setpoint is clamped to the device's reported
  `min_temp/max_temp` and snapped to its step in `build_command` (`_clamp`), so
  even a large bias can't drive an AC below the minimum it accepts.
- Mode selection: cooling demand → `cool` (or `dry` under the dew-point
  guard); off when no demand and hysteresis released.
- **Fan & swing passthrough:** if the AC advertises `fan_modes`/`swing_modes`,
  those are surfaced on the whole-home climate entity and forwarded to the
  AC(s) that support them.
- **Heating assist (optional):** when `ac_heating_assist` is enabled and the AC
  supports `heat`, the AC participates in heating per the arbiter (see
  [Control model](control-model.md#heatcool-coordination)).

### Write throttling

The proportional anchor nudges the setpoint most cycles, so re-issuing it each
time would flood the AC's radio. `_throttle_ac_setpoint`
(`control/throttle.py`) holds the last written value unless it moved ≥
`AC_SETPOINT_MIN_CHANGE` (0.5 °C) **and** ≥ `AC_SETPOINT_MIN_INTERVAL_SECONDS`
(180 s) elapsed, with an `AC_SETPOINT_KEEPALIVE_SECONDS` (900 s) re-assert;
held values become reconcile no-ops. The throttle resets on any non-cooling
command (so re-engaging cooling writes fresh). It complements the per-step diff
in `reconcile` — the step diff drops sub-step jitter, the throttle adds a time
floor on ≥-step drift.

## Idempotent commands (update minimisation)

Every adapter command passes through a diff against the device's last-known
state (`devices/reconcile.py`); a service call is issued **only when something
actually changes**:

- Skip setpoint writes when the desired value equals the current value within
  the device's step (e.g. 0.5 °C, or 1 % valve opening).
- Skip mode/fan/swing writes when the device is already in the requested state.
- Coalesce all triggers within one control cycle into at most one write per
  device, and debounce rapid sensor chatter.
- Cache last-commanded values in the coordinator and reconcile against reported
  state, so we neither spam devices nor fight manual/external changes.

This minimises Zigbee/RF and cloud traffic and extends TRV battery life.

## Manual-override takeover

The coordinator caches its last command per device, which makes external
intent detectable in the state listener: a state event whose *old* state
matched the active command and whose *new* state doesn't (mode, or target
setpoint by ≥ one device step) can only be a human or an external automation
— our own write echoes match the command, and a device that never reached it
is the watchdog's case instead. The ambiguous race (a human change while our
command is in flight) deliberately degrades into the watchdog path rather
than a wrong takeover.

While `DeviceRuntime.override_until` is set, `_control_one` still runs
`decide()` (the hysteresis latch stays current for the handback) but returns
the decision re-tagged `manual_override` with no writes — so the adapter
command, MPC observe/valve writes (no poisoned samples; the
`MAX_SAMPLE_DT_MIN` gap logic re-anchors on resume), the AC bias integral,
and the compliance watchdog are all suspended together. Starting an override
clears any watchdog streak for the same reason in reverse. The override ends
on expiry (checked per cycle), on the device going unavailable, on frost
protection (punches through unconditionally), or when the user interacts
with the whole-home climate entity (`clear_manual_overrides` — global intent
reasserts every device). Deadlines are monotonic and deliberately not
persisted: a restart reasserts control.

## Availability and graceful degradation

The single whole-home entity must never go dark because one device dropped off.
Each managed device and sensor is tracked independently:

- A TRV or AC reporting `unavailable`/`unknown` (or missing entirely) is
  **excluded from the current control cycle**; the remaining devices keep being
  controlled normally.
- The whole-home `climate` entity stays **available** as long as at least one
  managed device *or* a usable temperature source remains. It reports
  `unavailable` only if everything it could act on is gone.
- The **home-wide average** and any area aggregate are computed over
  *available* sensors only — an offline sensor is dropped from the mean rather
  than poisoning it (and an area whose configured sensor is offline falls back
  to the home average; see [Sensing](sensing.md)).
- Every device command is isolated: dispatched per-device and gathered with
  `return_exceptions=True`, so a timeout or error talking to one device is
  caught, logged, and contained — it can never abort the cycle for the others.
- A **command-ignored watchdog** catches the silent failure mode the above
  can't: service calls that *succeed* while the device's state never becomes
  the commanded HVAC mode (child lock, weak radio link, dying battery, a
  wedged integration). Each cycle compares the entity's reported mode to the
  just-built command; one unchanged commanded mode left unreflected past
  `COMMAND_IGNORED_SECONDS` (5 min) raises a per-device repair, cleared the
  moment the device converges. The threshold is time-based, not cycle-counted
  — refreshes also fire on every state change, and a burst of unrelated
  sensor updates must not fast-forward a device that merely reports slowly.
  Loudly failing devices (the bullet above) and unavailable ones are
  excluded; those have their own surfaces.
- Degraded status is surfaced for visibility: the diagnostic `status` sensor
  reads `degraded` and lists which devices are currently excluded in its
  `unavailable_devices` attribute. Devices rejoin automatically when they
  return.
- Learned MPC/observer state for an absent device is **retained, not reset**,
  so it resumes cleanly on reconnect.

### Post-restart warm-up

A tri-state `status` (`initializing` / `ok` / `degraded`) gates startup noise.
Right after a restart, devices and their area sensors typically haven't
reported in yet, so the coordinator reports `initializing` for a grace window
(`STARTUP_GRACE_SECONDS`, 120 s). The warm-up has two independent legs, and
both must land before the status settles: a usable home temperature, and every
managed device having reported in at least once. Area sensors usually beat the
devices by tens of seconds, so a device still joining keeps `initializing`
rather than flashing `degraded` (and its notification) on every restart — but
a device that *was* seen and then went away is genuine degradation, grace
window or not. While `initializing`, the **transient** repairs
(`no_temperature_source`, `stale_sensor`) are also held back. If the window
elapses with something still missing the gap is real: `status` becomes
`degraded` and, when there's no reading at all, the missing-source repair
fires. Static misconfigurations (inverted band, adaptive comfort without
an outdoor sensor) are *not* startup-transient and fire immediately.
`build_snapshot` sets a warm-up-unaware best-effort status; the coordinator
refines it. The `degraded` property is `status is DEGRADED`.

Next: [Persistence](persistence.md) — what survives restarts and how.
