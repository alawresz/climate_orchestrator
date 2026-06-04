# Testing

The integration is built test-first: pure control math gets exhaustive unit,
property, snapshot, and mutation tests; the HA-facing glue gets full
`pytest-homeassistant-custom-component` integration tests.

## Layout

`tests/unit/` mirrors the package (`control/`, `control/mpc/`, `devices/`,
`sensing/`) and holds every pure test, including the cross-module
property/regression/snapshot suites; `tests/ha/` holds the hass-fixture tests,
with the Home Assistant fixtures scoped to `tests/ha/conftest.py` (the root
`tests/conftest.py` carries only shared constants, and the engine-input
builders shared by the engine/property/regression suites live in
`tests/unit/control/builders.py`); the hass-side setup helpers
(TRV-with-number registry setup, desired-state and calibration-mode drivers)
live in `tests/ha/helpers.py`. Mutation testing targets `tests/unit/` alone
(`[tool.mutmut] tests_dir`), since those are the tests that kill `control/`
mutants.

## Test plan

- **Pure-function unit tests** (no HA): comfort index & dew point against
  reference tables; hysteresis state machine across engage/release/edge
  sequences; sensor aggregation & fallbacks; MPC sysid/observer/optimizer on
  synthetic first-order thermal simulations (assert convergence, stability, no
  windup, bounds respected).
- **Control-engine tests:** arbitration priority (frost > window > outdoor
  gating > demand), heat/cool mutual-exclusion invariant, deadband early-out,
  the worked example from requirements (home avg > 25 OR living room > 25
  engages AC; stays on until both ≤ target or room near heat band).
- **Adapter tests:** the `ClimateAdapter` issues the correct services for TRV
  valve %, TRV offset, and AC setpoint + mode over a generic HA `climate`
  entity, honouring `AdapterCapabilities` (capability gating, range/step
  clamping) with mocked services.
- **Integration tests (hass fixture):** config flow (device + sensor
  selection, overrides), entity creation snapshots, options/runtime entity
  changes re-trigger control, restart restores learned MPC + preset state.
- **Resilience tests:** a TRV or AC going `unavailable` excludes only that
  device while the home entity stays available and controls the rest; an
  offline sensor drops out of the home/area average; an area with an offline
  configured sensor falls back to the home average; one device raising an
  exception/timeout never aborts the cycle for the others; absent-device
  learned state is retained across the dropout.
- **Regression fixtures:** recorded sensor traces replayed through the control
  engine (`control/engine.py`) to catch behavioural drift.

A subagent-driven verification pass reviews coverage gaps before sign-off.

## Property tests (Hypothesis)

Hypothesis property tests check control invariants across generated inputs
(e.g. the heat/cool mutual exclusion, hysteresis monotonicity, bounds on
computed valves). CI runs with `HYPOTHESIS_PROFILE=ci` (no deadline —
loaded-runner deadline flake protection; the profile is registered in
`tests/conftest.py`).

## Snapshot tests (syrupy)

**syrupy** powers entity-state and diagnostics snapshot tests, plus dedicated
numeric regression snapshots (`tests/unit/test_snapshot_regression.py`,
`tests/unit/snapshots/`) pinning the exact comfort-curve and
adaptive-cooling-comfort outputs. Regenerate intentionally with
`pytest --snapshot-update`.

## Coverage gate

**pytest-cov** targets ≥ 95% line **+ branch** coverage on `control/`,
`sensing/`, `devices/`, gated in CI. Coverage is *not* forced in
`pyproject.toml` `addopts` — that would break single-file runs (`fail_under`)
and mutmut's per-mutant subset runs; CI passes `--cov` explicitly. Run it
locally with:

```bash
uv run pytest --cov=custom_components/climate_orchestrator
```

A `codecov.yml` splits coverage into components (control / devices / sensing /
shell) for visibility; the hard 95% gate stays in pytest.

## Mutation testing (mutmut)

Line/branch coverage and Hypothesis invariants don't prove the *math* is
right — a flipped sign or mis-scaled `dt` in the thermal model, optimizer, or
comfort curves can still pass. **mutmut** mutates the pure control modules and
surfaces any mutant the suite fails to kill.

- **Scope** (`[tool.mutmut]` in `pyproject.toml`): `paths_to_mutate` is
  `custom_components/climate_orchestrator/control/` only — the highest-value,
  subtlest code. `tests_dir` is `tests/unit/` (the pure tests are what kill
  `control/` mutants; skipping the hass-fixture suites makes mutation runs far
  faster). `also_copy` includes the whole `custom_components/` package because
  mutmut copies only `paths_to_mutate` into its `mutants/` work dir, but
  `control/` imports the rest of the package.
- **Running.** Run in the HA dev env (Python 3.14):

    ```bash
    uv run mutmut run
    uv run mutmut results
    ```

    On macOS, run it inside a Linux container instead — mutmut's runner
    uses a raw `os.fork`, which crashes on macOS ≥ 13.2 (the setproctitle
    after-fork problem, [boxed/mutmut#446](https://github.com/boxed/mutmut/issues/446)):

    ```bash
    docker run --rm -v "$PWD":/app -w /app ghcr.io/astral-sh/uv:python3.14-trixie \
      sh -c "uv sync --dev && uv run mutmut run; uv run mutmut results"
    ```

- **Triage.** For each surviving mutant, inspect it (`uv run mutmut show
  <id>`) and decide: a *meaningful* survivor (the mutation changes observable
  behaviour) gets a new test that kills it; an *equivalent* mutant (no
  observable behaviour change — e.g. a defensive clamp that current inputs
  never reach) is recorded with its rationale in the ledger below rather than
  papered over with a contrived test.

## Survivor ledger

A clean run is **845 mutants, 25 surviving (~97% killed)**. Every survivor
below has been triaged (rounds #98, #115, #127) and accepted as a residual;
**any survivor not on this list is a regression** and must be either killed
with a test or triaged onto this list with a rationale. Inspect any entry
with `uv run mutmut show <name>` (prefix:
`custom_components.climate_orchestrator.control.`).

| Module / mutants | Count | Why they survive |
|---|---|---|
| `mpc.controller` — `compute_valve_pct__mutmut_1` | 1 | Default-arg artifact: mutates the `max_opening_pct=100.0` default to `101.0`. Observably equivalent *because of* the final `[0, 100]` hardware clamp — any optimum above 1.0 clamps to 100 either way. |
| `mpc.optimizer` — `_rollout_cost__mutmut_3`, `optimize_valve__mutmut_{1,2,8,11,31}` | 6 | Default-arg artifacts (`horizon`, `effort_weight`, `max_opening` defaults) and bound-edge variants the bounded minimiser maps to the same clamped output. |
| `slope` — `temperature_slope_per_min__mutmut_{10,22,23,26,29,30}` | 6 | Equivalent variants of the least-squares slope accumulation: reordered/refactored sum terms that produce identical results for every reachable input. |
| `comfort` — `effective_temperature__mutmut_{1,2}` | 2 | Equivalent rearrangements of the blend expression. |
| `adaptive_bias` — `update_bias_integral__mutmut_{1,2}` | 2 | Default-arg artifacts on `decay`. |
| `adaptive_comfort` — `cool_edge_shift__mutmut_{3,5}` | 2 | Equivalent under the saturating-exponential contract (clamps already bound the output). |
| `engine` — `decide__mutmut_{84,118}` | 2 | Equivalent: alternate orderings of independent guard checks with identical decisions. |
| `runtime_stats` — `runtime_fraction__mutmut_{28,40}` | 2 | Equivalent boundary rewrites already pinned by the exact-value tests; the mutated forms compute the same fractions. |
| `hysteresis` — `evaluate_demand__mutmut_1` | 1 | Default-arg artifact. |
| `forecast` — `expand_forecast__mutmut_4` | 1 | Equivalent interpolation rewrite (same series for every step grid). |

!!! note
    Mutant *names are positional*: editing a function renumbers its mutants,
    so after touching a `control/` module expect renamed survivors and
    re-triage just those (as in round #127, where four renumbered survivors
    turned out to be genuinely new and were killed).

Next: [Tooling](tooling.md) — the lint/type/CI stack that runs all of this.
