# How it controls

This chapter explains the control loop from a user's point of view: what the two
setpoints mean, how a device decides to engage and release, and what happens on
every cycle. For the architecture and the maths behind it, see the
[developer guide](../internals/control-model.md).

## Two setpoints, not one

A normal thermostat has a single target and flips a heater on and off around it.
Climate Orchestrator uses a **band** with two edges:

- a **heat setpoint** — the bottom of the band; drop below it and heating engages.
- a **cool setpoint** — the top of the band; rise above it and cooling engages.

Between the two is a **neutral zone** where nothing runs. That gap keeps the
radiators and the AC from fighting (one heating while the other cools the same
air), so you can leave both heating and cooling armed all year and the system
does whichever the room needs, or nothing. Each preset (Home / Away / Sleep) is a
pair of these setpoints, editable live.

If you've configured only one kind of device the thermostat adapts: TRVs with no
AC become a plain **heat / off** thermostat with a single setpoint, and an AC
with no TRVs becomes **cool / off** — no inert second handle. (Turning on **AC
heating assist** makes an AC count as heat-capable, so an AC-only setup then
presents the full heat/cool band — a reversible heat pump.)

## Two temperatures, asymmetric trigger

For each device, Climate Orchestrator looks at two temperatures: the device's *own room*
and the *whole-home average*.

- **To start:** *either* temperature crossing an edge is enough. A cold bedroom
  turns on its own radiator; a house that's warm on average can switch on the AC
  in a room that's only borderline.
- **To stop:** *both* have to be back at target before the device backs off.

By default the home average is computed over the area sensors of rooms that
have managed devices. If you'd rather it reflect the *entire* home (or a
specific sensor you trust), pick your own **whole-home average temperature /
humidity sensors** in the integration options — they replace the computed
average wherever it's used. If an override sensor goes unavailable or stale,
the computed average quietly stands in, and the **Home average source**
diagnostic shows where the values are coming from (`external`, `computed`,
`fallback`, or `mixed` when temperature and humidity differ).

Don't want the home average influencing rooms at all? Turn off the **Home
average trigger** switch and every room runs purely on its own sensor (see the
[reference](../reference/entities.md)).

This "eager on, reluctant off" asymmetry prevents short-cycling on small sensor
fluctuations.

## Where it aims

When heating, Climate Orchestrator drives to **just past the heat setpoint** — the heat
setpoint plus the **Switching tolerance** (0.3 °C by default) — and stops.
Cooling mirrors it: down to just past the cool setpoint. Rooms settle at the
efficient end of the band: the cool end in winter, the warm end in summer. The
small overshoot past the edge also gives the anti-short-cycling its margin.

One band still doesn't suit every room equally — a per-area **band offset**
number can run a single room warmer or cooler than the rest; see
[Per-area band offsets](comfort-features.md#per-area-band-offsets).

## Feels-like, not just the number (Comfort index)

With **Comfort index targeting** on (default), the room and home temperatures are
converted to a humidity-adjusted "feels-like" (apparent) temperature before they
meet the band, so a muggy room is treated as warmer than the bare number. Cooling
then engages a little earlier in humid weather and a little later in dry weather.
**Comfort humidity influence** scales how strongly humidity counts (`0` = ignore
it, `1` = full feels-like, `>1` = amplify). A separate **dew-point guard** can put
the AC in dry mode when humidity is high.

No humidity sensors? Nothing breaks — the switch expresses *intent*, not a
requirement. Every consumer falls back to the plain dry-bulb temperature when
humidity is missing, and it degrades per room: a room with a humidity sensor
is judged on its feels-like value, a room without one on dry-bulb. Without any
humidity at all you simply get an ordinary dry-bulb thermostat: the *Home
feels-like temperature* sensor reads `unknown` and the dew-point guard never
engages. The moment a humidity sensor appears in an area, the comfort index
starts applying there — no toggling needed.

## Manual override takeover

Someone turns a radiator dial or points the AC remote — and most orchestrators
silently fight them back within a minute. Climate Orchestrator notices instead:
a device that *was* at its commanded state and then moved away (in mode, or in
target setpoint by at least one device step) without a command from us was
adjusted by a human (or an external automation), and the orchestrator **stands
back from that device** for the **Manual override duration** (default 60 min,
`0` disables the takeover).

While a device is overridden it receives no commands at all, its MPC learning
pauses (so the model isn't poisoned by samples it can't explain), and the
*HVAC action reason* sensor reports `Paused — manual override` for it (the
device's action sensor carries the remaining minutes). The override ends when
the timer runs out, when the device drops offline, when **frost protection**
needs it (safety always punches through), or the moment you touch the
whole-home thermostat — changing the preset, mode, or setpoints means "I'm in
charge again" and reasserts control over *every* device at once. Each start
and end is also announced as a
[bus event](services-automations.md#events).

## Safety guards

Layered over the decision, highest priority first: **frost protection** (force
heat if a room is freezing — overrides everything, even an open window) →
**window open** (a window/door open in a room stops that room's heating/cooling,
after an optional grace delay — though a portable AC can ignore *its own* room's
vent window via **AC ignores open windows**, while still stopping for a window
open in another room) → device capability (a radiator can't cool; an AC
only heats if allowed) → **outdoor gating** (don't heat when it's mild out or cool
when it's cool out).

## Each cycle, step by step

Climate Orchestrator re-evaluates whenever a relevant sensor changes (plus a
periodic safety check). A device under a
[manual takeover](#manual-override-takeover) is left alone entirely (unless
frost protection punches through); for every other managed device:

1. **Read the room** — the device's area temperature/humidity and the home
   average, as feels-like values when Comfort index targeting is on. An area
   sensor that has stopped reporting (older than the **Sensor staleness
   timeout**) is treated as missing and the home average is used instead.
2. **Place it against the band**, after any adaptive-comfort shift: below the heat
   setpoint → wants heat; above the cool setpoint → wants cooling; between →
   content.
3. **Decide, with memory** — apply the eager-on / reluctant-off rule, remembering
   what the device was already doing, and settle on heat, cool, or idle.
4. **Run the safety guards** — any can override the decision (order above).
5. **Send the smallest possible command** — anything that wouldn't change the
   device is skipped, to keep the radios quiet and the logs clean.

## Examples

All scenarios assume the **Home** preset (heat 20.5 °C / cool 24.5 °C) and
default settings.

**A humid living room calls in the AC.**
The living room reads 23.8 °C — under the cool edge — but it's muggy, and the
[comfort index](#feels-like-not-just-the-number-comfort-index) treats it as
~24.8 °C. That's over the edge, so the AC engages, commanded a setpoint *below*
the cool target so the room (not the AC's own sensor) is what reaches it.

**One hot room pulls in a comfortable one.**
The bedroom sits at 24.1 °C — fine on its own — but a hot kitchen has pushed
the *home average* over the cool edge. The OR-trigger engages the bedroom's AC
too; each room then releases individually as it cools past the target. Flip the
**Home average trigger** switch off and the bedroom would stay out of it.

**A window opens mid-heat-up.**
The study is heating toward 20.8 °C when a window opens. With a **Window open
delay** of 5 minutes, a quick airing changes nothing; if the window stays open
past the delay, that room's TRV stands down (the rest keep heating) and resumes
when it closes. If the room ever fell below the frost-protection temperature
(7 °C default), heating would override the open window.

**Muggy but not hot: dry mode.**
The bedroom reads 24.0 °C at 90 % humidity — under the cool edge, so no cooling
demand — but the dew point is over the 16 °C threshold. The dew-point guard
runs the AC's **dry** mode until the air dries out, without overcooling.

**Mild evening, nothing to do.**
Outdoor reads 14 °C with **outdoor-temperature gating** on: cooling is gated
off entirely (outdoor below 16 °C — a stray hot reading can't start the AC),
heating stays allowed, and with every room inside the band every device idles.
The cycle still runs each minute, re-asserting offsets and feeding the MPC
history.

Next: [Comfort features](comfort-features.md)
