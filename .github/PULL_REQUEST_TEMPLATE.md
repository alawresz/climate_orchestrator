<!--
Thanks for contributing! Two things to know up front:

* Commit messages follow Conventional Commits (https://www.conventionalcommits.org/)
  and drive automated releases: `feat:`/`fix:` on a `feat/**` or `fix/**`
  branch cuts a prerelease, and the merge to main cuts the release.
* Every change ships code + tests + docs together — the docs site chapters
  under docs/ are part of the deliverable, not an afterthought.

Conventions, testing strategy, and the release flow:
https://alawresz.github.io/climate_orchestrator/latest/project/contributing/
-->

## What & why

<!-- What does this change, and what problem does it solve? Link the issue if
there is one (e.g. "Fixes #123"). For behaviour changes, a short before/after
is worth more than prose. -->

## Checklist

- [ ] Commit/PR title follows Conventional Commits (`feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `ci:`, `chore:`)
- [ ] `uv run ruff check . && uv run ruff format --check .` passes
- [ ] `uv run mypy custom_components` passes
- [ ] `uv run pytest` passes, with tests covering the change (≥ 95% coverage gate)
- [ ] Docs updated (relevant chapters under `docs/`; entity changes also in `reference/entities.md`)
- [ ] `strings.json` and `translations/en.json` are byte-identical (if touched)
- [ ] Touched the control math in `control/`? Mention whether you ran mutation tests (`uv run mutmut run`)
