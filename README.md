# Climate Orchestrator

[![Release](https://img.shields.io/github/v/release/alawresz/climate_orchestrator?include_prereleases&sort=semver)](https://github.com/alawresz/climate_orchestrator/releases)
[![codecov](https://codecov.io/gh/alawresz/climate_orchestrator/graph/badge.svg)](https://codecov.io/gh/alawresz/climate_orchestrator)
[![CI](https://github.com/alawresz/climate_orchestrator/actions/workflows/ci.yml/badge.svg)](https://github.com/alawresz/climate_orchestrator/actions/workflows/ci.yml)
[![Docs](https://github.com/alawresz/climate_orchestrator/actions/workflows/docs.yml/badge.svg)](https://alawresz.github.io/climate_orchestrator/)
[![OpenSSF Best Practices](https://www.bestpractices.dev/projects/13105/badge)](https://www.bestpractices.dev/projects/13105)
[![OpenSSF Scorecard](https://api.scorecard.dev/projects/github.com/alawresz/climate_orchestrator/badge)](https://scorecard.dev/viewer/?uri=github.com/alawresz/climate_orchestrator)
[![HACS](https://img.shields.io/badge/HACS-Custom-41BDF5.svg)](https://github.com/hacs/integration)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)

One thermostat for the whole house. Instead of controlling each radiator valve
and air conditioner separately, you set a comfortable temperature range once and
Climate Orchestrator drives every device to keep each room inside it — heating cold
rooms, cooling hot ones, and preventing the two from fighting.

Each device follows the temperature sensor in its *own* Home Assistant area while
also watching the whole-home average, so one hot room can call in the AC even
when the rest of the house is fine. It controls off a humidity-adjusted
"feels-like" temperature, backs off for open windows and mild outdoor weather,
protects against frost, and — where radiator valves support it — can learn each
room's thermal behaviour to heat it more precisely over time.

You control it through a single `climate.climate_orchestrator` entity plus a set of live
toggles and numbers; there's no YAML to write.

## 📚 Documentation

**Full documentation lives at
[alawresz.github.io/climate_orchestrator](https://alawresz.github.io/climate_orchestrator/):**

- **[Getting started](https://alawresz.github.io/climate_orchestrator/latest/getting-started/introduction/)** —
  installation and the first-setup walkthrough.
- **[Guides & Reference](https://alawresz.github.io/climate_orchestrator/latest/guides/how-it-controls/)** —
  how the control works, every entity and setting, services, automations, and
  [troubleshooting](https://alawresz.github.io/climate_orchestrator/latest/reference/troubleshooting/).
- **[Internals & Project](https://alawresz.github.io/climate_orchestrator/latest/internals/architecture/)** —
  architecture, the control model and MPC maths, persistence, testing,
  tooling/CI, and the release process.

## Installation

Via [HACS](https://hacs.xyz/) (recommended):

[![Open your Home Assistant instance and add this repository to HACS.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=alawresz&repository=climate_orchestrator&category=integration)

1. Click the button above (it opens HACS with this repository pre-filled), or
   add it manually: HACS → ⋮ → **Custom repositories** → add
   `https://github.com/alawresz/climate_orchestrator` as type **Integration**.
2. Search for **Climate Orchestrator**, download it, and restart Home Assistant.
3. **Settings → Devices & Services → Add Integration → Climate Orchestrator**,
   then pick your TRV and AC `climate` entities.

Devices should be assigned to Home Assistant **areas** that have a temperature
(and ideally humidity) sensor configured (Settings → Areas → *Related
sensors*). Full steps, manual installation, upgrading, and removal:
[Installation](https://alawresz.github.io/climate_orchestrator/latest/getting-started/installation/)
· [First setup](https://alawresz.github.io/climate_orchestrator/latest/getting-started/first-setup/).

## Highlights

- **One control surface** — a single climate entity with a heating edge and a
  cooling edge drives all your TRVs and ACs, with a neutral band so the two
  never fight.
- **Area-matched sensing** — each device follows its own room's sensor; an
  asymmetric trigger engages on *room OR home average* and releases only when
  both are satisfied.
- **Feels-like control** — a humidity-adjusted comfort index, with a dew-point
  guard that can run the AC's dry mode.
- **Self-tuning AC drive** and **learning MPC valve control** (opt-in), with
  forecast preconditioning that pre-heats ahead of a cold spell.
- **Layered guards** — window-open (with grace delay), frost protection,
  outdoor-temperature gating, per-area comfort offsets, and AC drain protection
  that stops a tank-style AC before its condensate tank overflows.
- **Lives with you, not against you** — pick which presets to offer, **boost**
  for a timed extra push, and a manual-override takeover that stands back from
  any device you adjust by hand instead of fighting the change.
- **Observable & resilient** — per-device diagnostics, a tri-state status
  sensor, Repairs notices for silent misconfigurations (including devices that
  quietly ignore commands), bus events with self-clearing notifications,
  stale-sensor detection, and graceful degradation when devices drop offline.

## Development

Standalone `uv` project: `uv sync --dev`, then `uv run pytest` / `uv run mypy` /
`uv run ruff check .`. Docs preview: `uv run --group docs mkdocs serve`.
Conventions, testing strategy, and the release process live in the docs'
[Project chapters](https://alawresz.github.io/climate_orchestrator/latest/project/contributing/);
the architecture and control maths in the Internals chapters. Versioning is automated
with [python-semantic-release](https://python-semantic-release.readthedocs.io/)
from [Conventional Commits](https://www.conventionalcommits.org/); every change
ships code, tests, and docs together.

## Project status

The integration is feature-complete against the documented design and heavily
unit- and integration-tested. The hardware-specific TRV valve/offset writes are
**not yet validated on real devices**, so `target` calibration mode is the safe
baseline. As with any early-stage thermostat replacement, keep an independent
fallback for heating/cooling until it has proven itself in your setup. Issues
and PRs welcome — a debug log plus the diagnostics JSON makes reports
actionable (see
[Troubleshooting](https://alawresz.github.io/climate_orchestrator/latest/reference/troubleshooting/)).

## License

Released under the [MIT License](./LICENSE).
