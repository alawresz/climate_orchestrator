# Tooling and CI

The project develops against current Home Assistant's Python while keeping the
source loadable on the oldest supported HA install — two distinct version
gates, explained [below](#python-versions-two-gates) — with current best
practices enforced by ruff + mypy in CI.

## Stack at a glance

| Concern | Choice | Notes |
|---------|--------|-------|
| Env/deps | **uv** | Fast, lockfile, `uv run` for tasks. |
| Lint + format | **ruff** | Replaces black + flake8 + isort; format + lint in one. |
| Types | **mypy** (strict-ish) | pyright optional in editor. |
| Tests | **pytest** + **pytest-homeassistant-custom-component** | The standard HA harness: `hass` fixture, config-entry/flow helpers, service mocking. |
| Snapshots | **syrupy** | Entity-state and diagnostics snapshot tests. |
| Coverage | **pytest-cov** | Target ≥ 95% line + branch on `control/`, `sensing/`, `devices/`; gate in CI. |
| Hooks | **pre-commit** | ruff + mypy + end-of-file/whitespace. |
| CI | **GitHub Actions** | See below. |
| HA validation | **hassfest** + **HACS action** | Manifest/structure and HACS packaging validation. |

## uv and the lockfile

**uv** manages the environment and dependencies through a committed lockfile
(`uv.lock`), so every developer and every CI run resolves the exact same
dependency set; `uv sync --dev` reproduces it and `uv run <task>` executes
inside it. CI installs uv (with Python 3.14, HA's runtime) via
`astral-sh/setup-uv`.

## Python versions: two gates

The integration is **not installed as a Python package**: the release zip is
built from `custom_components/climate_orchestrator/` alone, HACS copies that
folder into the user's config, and HA imports it as plain modules. No packaging
metadata travels with it — the only dependency file HA reads is
`manifest.json` (that's how `scipy` gets installed). `pyproject.toml` is the
dev-tooling project only (`[tool.uv] package = false`), so its constraints
never gate a user's install. Two settings therefore govern two different
things:

- **`requires-python` (currently `>=3.14.2`)** — the dev/test environment
  floor, tracking current HA's runtime. It exists so uv resolves one coherent
  lockfile instead of keeping resolution forks for old interpreters (pinned to
  ancient, CVE-laden HA releases). mypy's `python_version` matches it because
  mypy parses the installed `homeassistant` sources.
- **`ruff target-version` (currently `py313`)** — the source-compatibility
  floor: the oldest Python an HA install we support might run. Since nothing
  enforces a version at install time, ruff is the only guard that the code
  stays *loadable* there.

This split is why `from __future__ import annotations` stays in every module:
the `TC` ruleset moves type-only imports into `if TYPE_CHECKING:` blocks, and
on pre-3.14 interpreters (eager annotation evaluation, no PEP 649) those
annotations would otherwise `NameError` at import. The future imports become
droppable only when the minimum supported HA guarantees Python 3.14 and
`target-version` is bumped to match.

## ruff ruleset rationale

ruff provides both formatting and linting in one tool. Beyond the basics, the
ruleset enables: pycodestyle, pyflakes, isort, pyupgrade, flake8-bugbear,
comprehensions, simplify, and async checks. These back the project's coding
conventions:

- **Type hints everywhere** — fully annotated public and internal APIs;
  `from __future__ import annotations`. No `Any` without justification.
- **Dataclasses & immutability** — `@dataclass(frozen=True, slots=True)` for
  value objects (`SmartClimateData`, `DeviceReading`, `Band`, `DeviceState`,
  `DeviceCommand`, `AdapterCapabilities`, `Writes`,
  `DeviceInput`/`GlobalInput`/`DeviceDecision`,
  `Sample`/`ThermalParams`/`KalmanState`). Frozen by default; mutable runtime
  state lives only in the coordinator.
- **Enums over magic strings** — `StrEnum` for `Demand`, `DeviceKind`, `Mode`,
  and `Status`; calibration modes and other fixed strings are named constants
  in `const.py`, never inline literals.
- **Pure functions for logic** — control math is side-effect-free and
  dependency-injected, keeping I/O at the edges (coordinator/adapter).
- **Modern syntax** — `X | None` unions (PEP 604), `match` where it clarifies,
  `pathlib`, f-strings, comprehensions over manual loops,
  `functools.cached_property` where apt.
- **Async correctness** — no blocking calls in the event loop; `async`/`await`
  throughout; `asyncio.gather` for parallel device commands; HA's `async_*`
  APIs only.
- **Errors & logging** — narrow exception handling (no bare `except`), typed
  custom exceptions, structured `_LOGGER` messages with lazy `%` formatting.
- **Docstrings** on modules and public callables; self-documenting names
  elsewhere.

## mypy strict config

mypy runs in strict-ish mode (`disallow_untyped_defs`, `warn_return_any`) over
`custom_components/climate_orchestrator`:

```bash
uv run mypy custom_components/climate_orchestrator
```

## pre-commit

pre-commit hooks run ruff (lint + format), mypy, end-of-file/whitespace fixers,
a codespell pass (with `hass` whitelisted — it's the Home Assistant
fixture/handle, not a misspelt "hash"), and the `strings.json` ↔
`translations/en.json` sync check (see
[Contributing](contributing.md#project-conventions)).

## CI workflows (GitHub Actions)

CI is `.github/workflows/ci.yml`, which also unlocks HACS distribution. Jobs
are **path-scoped** by a leading `changes` job so a docs-only change doesn't
pay for the full test run: a pull request is classified by its diff against
the base branch, a push by its diff against the **last release tag** — exactly
the commits semantic-release would put in the next release, so a code push can
never reach a release with its tests skipped by a later docs-only push. PRs
from this repo's `feat/**`/`fix/**` branches skip CI entirely (the push event
already covers them); fork PRs and other branch names — Dependabot's
`dependabot/**` in particular — still run, since those have no push runs to
lean on. A concurrency group cancels obsolete in-flight runs
when the same ref is pushed again, and every job carries a 30-minute timeout
(here and in the other workflows) so nothing can burn runners for GitHub's
6-hour default. The jobs:

- **lint** (every change) — `uv lock --check` (the committed lockfile must
  match `pyproject.toml`), `uv run ruff check .` + `ruff format --check`,
  codespell (same pinned hook as pre-commit), the `strings.json` ↔
  `translations/en.json` byte-identity check, and two workflow linters:
  **zizmor** (security) and **actionlint** (correctness: expression errors +
  shellcheck over `run:` blocks, via the `actionlint-py` binary wheel).
- **test** (code changes) — `uv run mypy custom_components/climate_orchestrator`
  and `uv run pytest --cov-report=xml --junitxml=junit.xml`. Coverage goes to
  Codecov, and the JUnit file feeds **Codecov Test Analytics** (per-test run
  times, failure rates, flake detection — uploaded with
  `report_type: test_results`, even when pytest fails, since failure data is
  the point). CI pytest runs with `--timeout=120` (pytest-timeout; a CI-only
  flag, like coverage) and `HYPOTHESIS_PROFILE=ci` (no deadline —
  loaded-runner deadline flake protection).
- **docs** (docs changes) — the strict no-deploy MkDocs build; the same
  command as the Pages deploy, so a broken link or anchor fails the PR.
- **hassfest** (integration changes) — `home-assistant/actions/hassfest`
  validates the manifest/structure, including `strings.json`.
- **hacs** (integration changes) — `hacs/action` with `category: integration`.
  `ignore: brands` stays: that check looks for the domain in
  `home-assistant/brands`, while since HA 2026.3 the icons ship *inside* the
  integration — `custom_components/climate_orchestrator/brand/icon.png` +
  `icon@2x.png`, served via the local brands proxy API and taking priority
  over the CDN; the SVG source stays in the repo-root `brand/`.

Two scheduled workflows complement CI; each files (or bumps) a `ci`-labelled
tracking issue when it fails and closes it again on the first green run,
with a comment naming the commit it recovered at:

- A weekly **`links.yml`** runs lychee over the README, the changelog, the
  docs chapters, and the issue/PR templates to catch dead *external* links
  (internal docs links are gated per-PR by the strict MkDocs build).
- A weekly **`ha-dev.yml`** ("HA compatibility") canary covers both ends of
  the supported HA range: the test suite **plus mypy** against HA's latest
  *pre-release* (uv `--prerelease=allow` upgrade over the locked venv — type
  errors often surface upstream breakage before tests do), and the test suite
  against the **oldest supported HA** (hacs.json's floor, currently 2025.2,
  via the matching PHACC pin in an unlocked Python 3.13 env) — the claimed
  floor is only honest while something tests it. The floor run excludes the
  syrupy snapshot tests: their on-disk format tracks the locked syrupy (5.x),
  which the old PHACC's syrupy 4.x can't read, and the math they pin doesn't
  vary with HA. Scheduled, so neither gates PRs; a red floor run means either
  a compat fix or raising the floor.

Three further automation workflows round things out. A weekly
**`scorecard.yml`** runs OpenSSF Scorecard over the repo's supply-chain
practices (pinned actions, token permissions, update tooling), feeding the
Security → Code scanning panel and the README badge. **`codeql.yml`** runs
CodeQL on every push to main and weekly, analyzing both the Python source and
the GitHub Actions workflows (the `actions` query pack complements zizmor on
workflow-injection patterns) — modest expected Python yield next to
ruff/mypy, but it keeps security static analysis continuous.
The repo also ships a root **`SECURITY.md`** (private vulnerability
reporting, supported versions, artifact verification).
**`dependabot-automerge.yml`** arms auto-merge (squash) on Dependabot's
grouped minor/patch PRs once CI is green — semver-major bumps stay manual; it
relies on the repo's "Allow auto-merge" setting plus required status checks
on `main`, and accepts that the GITHUB_TOKEN-performed merge commit triggers
no push CI of its own (the PR was fully gated, `chore(deps)` never releases,
and the next push diffs against the last release tag, which includes it).

**`docs.yml` (documentation deploy):** builds the versioned MkDocs site with
mike and publishes it to GitHub Pages through the Actions deploy path. Only
released versions are published: a stable release deploys **X.Y** and
re-points **latest**, dispatched explicitly from `release.yml`. There is
deliberately no `release` trigger — PSR publishes with the release app's
token, whose release events fire for stables and prereleases alike, and a
prerelease must never move the docs. `workflow_dispatch` can bootstrap or
repair any version, or refresh the current one after a docs-only commit
that cut no release. There is no
rolling *dev* build of `main` — semantic-release versions nearly every
change, so main never drifts far ahead of the newest numbered docs. The PR
gate (`mkdocs build --strict`) lives in `ci.yml`; see [Releases](releases.md)
for where the dispatch hooks into the release flow.

`__init__.async_migrate_entry` scaffolds config-entry migration
(`CONFIG_ENTRY_VERSION`, refuses future-version downgrades).
`quality_scale.yaml` tracks the HA integration quality scale — maintenance
rules in [Contributing](contributing.md).

## Supply-chain notes

- All third-party actions are **pinned by commit SHA** with version comments;
  Dependabot keeps them current.
- **zizmor** lints the workflows themselves in CI, with the few accepted
  findings suppressed inline with rationale (the release workflow's
  `workflow_run` trigger + credential persistence for the PSR push, and the
  unpinnable `hassfest@master`/`hacs@main` branches).
- The release job additionally guards on
  `head_repository == github.repository`.
- Release artifacts carry build provenance attestation — see
  [Releases](releases.md).

Next: [Releases](releases.md) — how green CI becomes a tagged, HACS-consumable
release.
