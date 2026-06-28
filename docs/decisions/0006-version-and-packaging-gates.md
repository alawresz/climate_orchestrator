# ADR-0006: Version and packaging gates

**Status:** Accepted
**Date:** 2026-06 (retrospective)

## Context

Three version-shaped facts about this project look contradictory at a glance and
will baffle anyone who finds them cold:

- `pyproject.toml` declares `requires-python = ">=3.14.2"`.
- ruff is pinned to `target-version = "py313"`.
- `pyproject`'s own `version` is frozen at `"0.0.0"`, while `manifest.json`
  carries the real, release-stamped version and `hacs.json` pins HA `2025.2.0`.

Each is deliberate, and the reasons are non-obvious. This ADR records them so
they aren't "fixed" into breakage.

## Decision

**1. `requires-python >=3.14.2,<3.15` is a dev-environment statement, not the
runtime floor.** It exists for lockfile coherence — `uv` resolves the dev
toolchain against the interpreter the maintainer runs (3.14). A HACS-installed
integration is *not* pip-installed: the release is a zip of `custom_components/…`
with **no packaging metadata**, so `requires-python` is never consulted at
install or runtime. Nothing enforces it on users.

The **upper bound is load-bearing**, not cosmetic. Unbounded, `uv`/Dependabot
do universal resolution across all future Python and fork a `python >= 3.15`
branch; no Home Assistant satisfies that branch (HA pins conflicting `aiohttp`
versions across python ranges), so resolution fails. For `uv lock` that is
merely an extra fork, but for **Dependabot it is fatal**: it reports "can't
resolve your Python dependency files" and silently stops opening *security*
update PRs (this blocked the pyjwt and cryptography advisories). Capping at the
dev interpreter's minor (`<3.15`) removes the impossible fork. Raise the floor
*and* the cap together when adopting 3.15.

**2. ruff's `target-version = "py313"` is the real install-time floor.** Since
no metadata gates installation, the only thing that actually keeps the source
runnable on the oldest supported HA is the syntax/feature level the linter
allows. HA 2025.2 ships on Python 3.13, so the source must stay py313-clean —
hence the lint target, independent of the dev interpreter. (This is also why
`from __future__ import annotations` is load-bearing and enforced.)

**3. `pyproject` version frozen at `0.0.0`; python-semantic-release stamps only
`manifest.json`.** `manifest.json` is what HA and HACS read, and the git tag is
the source of truth. If PSR also bumped `pyproject`'s version, every release
would change the virtual-root version recorded in `uv.lock` and invalidate it
(`uv lock --check` fails in CI). Freezing `pyproject` at `0.0.0` and pointing
PSR's `version_variables` solely at `manifest.json` keeps the lockfile stable
across releases.

**4. The HA floor is 2025.2**, set by [ADR-0003](0003-area-sensor-resolution.md)
(`area.temperature_entity_id`), recorded in `hacs.json` and guarded by the floor
CI canary running the suite against a pinned 2025.2 environment.

## Consequences

- **Do not** "align" `requires-python` with the ruff target, drop its upper
  bound, or bump `pyproject`'s version to match `manifest.json` — each change
  breaks a real invariant (lockfile coherence; Dependabot's ability to resolve
  and open security PRs; the install-time floor) for a cosmetic tidy.
- The *runtime* floor lives in `hacs.json` + the ruff target + the floor canary,
  **not** in `requires-python`.
- Raising the floor (e.g. to adopt a newer HA API) means: bump `hacs.json`,
  bump the ruff target if the Python minimum moves, and repin the canary.
