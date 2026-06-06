# ADR-0007: Release pushes use a dedicated GitHub App token

**Status:** Accepted
**Date:** 2025-06 (retrospective)

## Context

`main` is protected by a repository **ruleset**: required status checks, no
force-push, no deletion, with a small bypass list. python-semantic-release, run
in CI on merge to `main`, needs to push a release commit (`chore(release): …`)
and a tag back to `main` — which the ruleset blocks unless the pushing actor is
a bypass actor.

The natural first choices both fail, in ways that are easy to forget:

- **The default `GITHUB_TOKEN`** cannot be granted ruleset bypass; pushes with
  it are rejected (`GH013`).
- **Adding "GitHub Actions" as a bypass actor** is impossible on a *user-owned*
  (non-organization) repo: the API rejects it with
  *"Actor GitHub Actions integration must be part of the ruleset source or owner
  organization"* (422), and the UI offers no way to add it.

So on a personal repo there is no built-in actor that can both run CI and bypass
the ruleset.

## Decision

Use a **dedicated GitHub App** as the release identity. The release workflow
mints a short-lived installation token
(`actions/create-github-app-token`, `permission-contents: write`, from
`secrets.RELEASE_APP_ID` / `RELEASE_APP_PRIVATE_KEY`) and uses it for the PSR
push, the tag, and the downstream dispatch. The App **is** addable to the
ruleset bypass list (it is a first-class actor the owner controls), so its
pushes are accepted while `main` stays protected against everything else.

## Options Considered

| Option | Outcome |
|--------|---------|
| `GITHUB_TOKEN` pushes to `main` | Rejected by the ruleset (`GH013`) |
| Add "GitHub Actions" as a bypass actor | Impossible on a user repo (422) |
| Drop to classic branch protection | Loosens protection, and Scorecard can't read classic protection via the API — regresses the security posture |
| Personal access token (PAT) | Works, but ties releases to a human account and a long-lived secret; worse blast radius than a scoped App token |
| **Dedicated GitHub App (chosen)** | Addable to bypass; short-lived scoped token; not tied to a person |

## Consequences

- **Easier:** automated releases coexist with a protected `main`; the token is
  short-lived and narrowly scoped (`contents: write`), satisfying the
  Dangerous-Workflow / least-privilege checks.
- **Operational cost:** two repository secrets (`RELEASE_APP_ID`,
  `RELEASE_APP_PRIVATE_KEY`) and an App whose private key must be rotated if
  leaked; the App must remain in the ruleset bypass list.
- **Do not** revert to `GITHUB_TOKEN` or classic protection to "simplify" —
  both reintroduce a problem this solved (a blocked release, or a Scorecard
  regression). The zizmor "github-app token" advisory is addressed by scoping
  the mint to `permission-contents: write`.
