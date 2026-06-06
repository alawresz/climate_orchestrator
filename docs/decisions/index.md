# Architecture decisions

This section records the significant, hard-to-reverse decisions behind Climate
Orchestrator as [Architecture Decision Records](https://adr.github.io/) (ADRs):
short documents capturing the context, the options weighed, the choice, and its
consequences — so the *why* survives long after the code that resulted from it.

## Conventions

- **Numbering is creation order**, not chronological decision order. An ADR
  written to capture an earlier decision still takes the next free number; its
  **Date** field carries the real chronology.
- **ADRs are append-only.** Once *Accepted* an ADR is not edited away — if a
  later decision overrides it, the old one is marked *Superseded by ADR-NNNN*
  and a new ADR is written.
- **Status** is one of *Proposed*, *Accepted*, *Superseded*, or *Deprecated*.

## Records

Numbers are creation order; the **Decided** column is the real chronology
(records 0002–0007 were written retrospectively to capture earlier decisions).

| ADR | Title | Status | Decided |
|-----|-------|--------|---------|
| [0001](0001-device-profiles.md) | Device profiles for hardware quirks | Accepted | 2026-06 |
| [0002](0002-pure-control-core.md) | A pure, Home Assistant-free control core | Accepted | 2025-06 |
| [0003](0003-area-sensor-resolution.md) | Resolve room sensors from the area registry | Accepted | 2025-06 |
| [0004](0004-trv-calibration-mpc.md) | TRV calibration strategies + MPC valve control | Accepted | 2025-06 |
| [0005](0005-store-schema-versioning.md) | Store schema versioning with downgrade-safe discard | Accepted | 2025-06 |
| [0006](0006-version-and-packaging-gates.md) | Version and packaging gates | Accepted | 2025-06 |
| [0007](0007-github-app-release.md) | Release pushes use a dedicated GitHub App token | Accepted | 2025-06 |
