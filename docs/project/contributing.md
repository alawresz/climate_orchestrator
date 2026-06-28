# Contributing

The repo is laid out as a standalone project (`pyproject.toml`, `.venv`,
`custom_components/`, `tests/`); deploy by copying
`custom_components/climate_orchestrator/` into your HA config (see the
[installation guide](../getting-started/installation.md)).

## Dev environment setup

Uses [uv](https://github.com/astral-sh/uv), [ruff](https://docs.astral.sh/ruff/),
[mypy](https://mypy-lang.org/), and [pytest](https://pytest.org/) with
[`pytest-homeassistant-custom-component`](https://github.com/MatthewFlamm/pytest-homeassistant-custom-component).

```bash
uv venv --python 3.14 && uv sync --dev   # create env, install deps
uv run ruff check . && uv run ruff format --check .
uv run mypy custom_components/climate_orchestrator
uv run pytest                            # fast: tests only
uv run pytest --cov=custom_components/climate_orchestrator   # with coverage (CI gate: 95%)
uv run mutmut run                        # mutation-test the control/ math
```

See [Testing](testing.md) for the test layout, the coverage gate, and how to
run and triage mutation tests, and [Tooling](tooling.md) for what CI enforces.

### Local docs preview

The documentation site is MkDocs Material; preview it locally without adding
docs dependencies to the project environment:

```bash
uv run --group docs mkdocs serve
```

## Project conventions

- **Every change ships code + tests + docs.** Contributions are expected to
  keep docs and tests in step with behaviour: user-facing changes update the
  user documentation (especially the
  [controls & settings reference](../reference/entities.md) and
  [how it controls](../guides/how-it-controls.md)), design changes update
  the relevant developer chapter, and every change ships with
  tests (pure unit tests for logic, `pytest-homeassistant-custom-component`
  for HA-facing glue) with `ruff` and `pytest` green.
- **`strings.json` is byte-identical to `translations/en.json`.** hassfest
  validates `strings.json`; the two files are sync-checked in CI and
  pre-commit, so edit them together (or copy one over the other) — a drifted
  pair fails the gate.
- **Conventional commit types cut releases.** `fix:` → patch, `feat:` → minor,
  `feat!:`/`BREAKING CHANGE:` → major; pushing a green `feat/*` or `fix/*`
  branch cuts an `rcN` prerelease and merging to `main` cuts the stable
  release — so write commit messages as if they ship, because they do. See
  [Releases](releases.md).
- **Maintain `quality_scale.yaml`.**
  `custom_components/climate_orchestrator/quality_scale.yaml` tracks the HA
  integration quality scale honestly (45 done / 7 exempt; no remaining
  todos). A change that affects a tracked rule (new entity behaviour,
  diagnostics, config flow, etc.) updates the corresponding entry — including
  its `comment` rationale — in the same PR.

!!! note "Coding style"

    The full set of code conventions (typing, frozen dataclasses, enums over
    magic strings, pure functions, async correctness) lives in
    [Tooling](tooling.md#ruff-ruleset-rationale) and is enforced by ruff +
    mypy in CI.

Next: head back to the [architecture overview](../internals/architecture.md), or the
[user guide introduction](../getting-started/introduction.md).
