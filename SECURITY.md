# Security policy

## Supported versions

Releases are rolling (semantic-release cuts a version for nearly every
change), so only the **latest release** receives fixes. If you are on an
older version, update through HACS before reporting.

## Reporting a vulnerability

Please use GitHub's private vulnerability reporting:
**[Report a vulnerability](https://github.com/alawresz/climate_orchestrator/security/advisories/new)**
— do not open a public issue for anything security-sensitive.

Helpful details to include: the integration version (HACS → Climate
Orchestrator), your Home Assistant version, and a description of the issue
with reproduction steps if possible. Do **not** attach diagnostics dumps to a
report until asked — they can contain entity names and layout details of your
home.

This is a single-maintainer project: reports are handled on a best-effort
basis. Confirmed vulnerabilities are fixed in a regular release and noted in
the changelog.

## Scope

The integration runs inside Home Assistant with the privileges of any custom
component — there is no sandbox. Things that are *in scope*: anything that
could let the integration damage a Home Assistant installation beyond its
job of controlling the configured climate devices, leak data it has no
business reading, or be leveraged through crafted entity states. Issues in
Home Assistant itself, HACS, or device firmware belong upstream.

## Verifying release artifacts

Every release zip carries build provenance. Verify the asset HACS installs:

```
gh attestation verify climate_orchestrator.zip -R alawresz/climate_orchestrator
```

or offline against the `*.intoto.jsonl` bundle attached to each release
(`cosign verify-blob --bundle`).
