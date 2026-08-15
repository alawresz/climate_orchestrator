# CHANGELOG

<!-- version list -->

## v0.33.2 (2026-08-15)

### Bug Fixes

- Remove unnecessary noqa
  ([`f73cc3d`](https://github.com/alawresz/climate_orchestrator/commit/f73cc3d4263762bf4e9e4e03812fd4cb2a0d79bf))

### Chores

- Bump https://github.com/astral-sh/ruff-pre-commit from v0.16.1 to 0.16.2
  ([#48](https://github.com/alawresz/climate_orchestrator/pull/48),
  [`6277e02`](https://github.com/alawresz/climate_orchestrator/commit/6277e02e286c20d39edd88ffd783a789f90ec4dc))

- Bump pillow from 12.2.0 to 12.3.0
  ([#46](https://github.com/alawresz/climate_orchestrator/pull/46),
  [`86b7ad7`](https://github.com/alawresz/climate_orchestrator/commit/86b7ad7aed84a0509cf77180cd917e04ddf1c6c9))

- Bump pyjwt from 2.12.1 to 2.13.0 ([#45](https://github.com/alawresz/climate_orchestrator/pull/45),
  [`bbdd330`](https://github.com/alawresz/climate_orchestrator/commit/bbdd3309694394b371cce417652aa839a966eb3e))

- Bump pymdown-extensions from 11.0 to 11.0.1
  ([#47](https://github.com/alawresz/climate_orchestrator/pull/47),
  [`20a82dd`](https://github.com/alawresz/climate_orchestrator/commit/20a82dd2e20493b6c31646a23329516cf6c85c6c))

- Bump the github-actions group with 4 updates
  ([#50](https://github.com/alawresz/climate_orchestrator/pull/50),
  [`414de66`](https://github.com/alawresz/climate_orchestrator/commit/414de665ff4e4cd6b49221d8baec1266db527b87))

- Bump the python-tooling group across 1 directory with 8 updates
  ([#49](https://github.com/alawresz/climate_orchestrator/pull/49),
  [`07e8bae`](https://github.com/alawresz/climate_orchestrator/commit/07e8bae43d501f543f6787a86068557b6a2b4486))

- Remove stray newline in `adding-hardware.md`
  ([`4845809`](https://github.com/alawresz/climate_orchestrator/commit/4845809e112be0bac2b1d8f63b58757d35a0abbb))

### Testing

- Add snapshots for regression tests on adaptive cooling and comfort curve
  ([`77db966`](https://github.com/alawresz/climate_orchestrator/commit/77db966e707a0939c588a7098d9c49363d51b3b3))

- Drop the duplicate snapshot file
  ([`4e92272`](https://github.com/alawresz/climate_orchestrator/commit/4e92272dd8e7b4c3ced61aa8b1f7632b6b6b9483))

- Own the snapshot directory instead of inheriting it
  ([`4b751af`](https://github.com/alawresz/climate_orchestrator/commit/4b751af36ddad134dcf14c30517c37232f1048fb))

- Reorganize integration test setup to ensure correct control cycle execution in TRV heating
  scenarios
  ([`b516654`](https://github.com/alawresz/climate_orchestrator/commit/b516654715395a332bf636ffa9e98c66e698cf7f))

- Switch to async `set_desired_preset` and refactor integration tests
  ([`0db911b`](https://github.com/alawresz/climate_orchestrator/commit/0db911b70065c8dfa63bcca1f3da65e3dfad3349))


## v0.33.1 (2026-08-06)

### Bug Fixes

- Defer scipy-backed MPC imports to async executor for non-blocking I/O
  ([`2c6b933`](https://github.com/alawresz/climate_orchestrator/commit/2c6b9331317ddba798c10f33a708b3a7f8e00635))

### Chores

- Bump actions/attest-build-provenance from 4.1.0 to 4.1.1 in the github-actions group
  ([#20](https://github.com/alawresz/climate_orchestrator/pull/20),
  [`a3146f2`](https://github.com/alawresz/climate_orchestrator/commit/a3146f28f8f21b5d69d42a3921cdb84fd90f6e76))

- Bump gitpython from 3.1.50 to 3.1.54
  ([#38](https://github.com/alawresz/climate_orchestrator/pull/38),
  [`b6b6de3`](https://github.com/alawresz/climate_orchestrator/commit/b6b6de343102e2b84422ccda7810fcb27799d915))

- Bump https://github.com/astral-sh/ruff-pre-commit from v0.15.16 to 0.15.20
  ([#19](https://github.com/alawresz/climate_orchestrator/pull/19),
  [`1812fce`](https://github.com/alawresz/climate_orchestrator/commit/1812fcea163ab00bf0648ab45b25347693b8e973))

- Bump https://github.com/astral-sh/ruff-pre-commit from v0.15.20 to 0.15.21
  ([#27](https://github.com/alawresz/climate_orchestrator/pull/27),
  [`e89ff6e`](https://github.com/alawresz/climate_orchestrator/commit/e89ff6e0b2cada04f102206a25e4302b63e578b5))

- Bump https://github.com/astral-sh/ruff-pre-commit from v0.15.21 to 0.16.0
  ([#39](https://github.com/alawresz/climate_orchestrator/pull/39),
  [`54a8514`](https://github.com/alawresz/climate_orchestrator/commit/54a8514b5283ee0f35a2cb2225ace86b541b1e38))

- Bump https://github.com/astral-sh/ruff-pre-commit from v0.16.0 to 0.16.1
  ([#42](https://github.com/alawresz/climate_orchestrator/pull/42),
  [`9af9cfc`](https://github.com/alawresz/climate_orchestrator/commit/9af9cfc2ffa0aeccc09c0d4ea0265a1e765fcca2))

- Bump https://github.com/codespell-project/codespell from v2.4.2 to 2.4.3
  ([#26](https://github.com/alawresz/climate_orchestrator/pull/26),
  [`524e371`](https://github.com/alawresz/climate_orchestrator/commit/524e371fa5d914b7ceae0617fd8b49067361b65f))

- Bump https://github.com/pre-commit/mirrors-mypy from v2.1.0 to 2.2.0
  ([#22](https://github.com/alawresz/climate_orchestrator/pull/22),
  [`96a19ca`](https://github.com/alawresz/climate_orchestrator/commit/96a19ca5df9cf2499c7852c78e22447e8c84935b))

- Bump lycheeverse/lychee-action from 2.8.0 to 2.9.0 in the github-actions group
  ([#28](https://github.com/alawresz/climate_orchestrator/pull/28),
  [`abbbf44`](https://github.com/alawresz/climate_orchestrator/commit/abbbf4428e3ad43a05be1b57be5ab7790e5bf4d4))

- Bump mdformat-mkdocs from 5.1.4 to 5.2.0 in the python-tooling group
  ([#21](https://github.com/alawresz/climate_orchestrator/pull/21),
  [`204d86f`](https://github.com/alawresz/climate_orchestrator/commit/204d86f6ba1c3125af35586ef4cdc2645790bd47))

- Bump the github-actions group across 1 directory with 5 updates
  ([#40](https://github.com/alawresz/climate_orchestrator/pull/40),
  [`81d2119`](https://github.com/alawresz/climate_orchestrator/commit/81d2119fc574d2a917dd52c0909c0b1e3dbe0b29))

- Bump the github-actions group with 3 updates
  ([#44](https://github.com/alawresz/climate_orchestrator/pull/44),
  [`38a3cac`](https://github.com/alawresz/climate_orchestrator/commit/38a3cacf277da3fbf68683d147264b649ddc76c9))

- Bump the github-actions group with 6 updates
  ([#23](https://github.com/alawresz/climate_orchestrator/pull/23),
  [`f1f6849`](https://github.com/alawresz/climate_orchestrator/commit/f1f68495c39202c47a72914082d88b17268529b2))


## v0.33.0 (2026-06-28)

### Chores

- Bump actions/checkout from 6.0.3 to 7.0.0
  ([#15](https://github.com/alawresz/climate_orchestrator/pull/15),
  [`01a09f0`](https://github.com/alawresz/climate_orchestrator/commit/01a09f0d161bf08537c7c73e2da20dd4e464baa9))

- Bump https://github.com/astral-sh/ruff-pre-commit from v0.15.15 to 0.15.16
  ([#10](https://github.com/alawresz/climate_orchestrator/pull/10),
  [`b16ebfe`](https://github.com/alawresz/climate_orchestrator/commit/b16ebfe6af09e35866b8f8345f0ded52274e4309))

- Bump python-semantic-release/publish-action from 68eaac9f1f594e9ec4b985245d06355734f43eea to
  310a9983a0ae878b29f3aac778d7c77c1db27378
  ([#12](https://github.com/alawresz/climate_orchestrator/pull/12),
  [`13ecf4f`](https://github.com/alawresz/climate_orchestrator/commit/13ecf4fd05666664d6c150db0522cfb9a54588bd))

- Bump the python-tooling group across 1 directory with 4 updates
  ([#18](https://github.com/alawresz/climate_orchestrator/pull/18),
  [`5a273d5`](https://github.com/alawresz/climate_orchestrator/commit/5a273d500d2e8524a8fbf02a935f2aea0e81153f))

- Bump zeroconf from 0.148.0 to 0.149.16
  ([#17](https://github.com/alawresz/climate_orchestrator/pull/17),
  [`983d05e`](https://github.com/alawresz/climate_orchestrator/commit/983d05e3c2de94c69d71e553224c683be22fcb82))

- Cap requires-python <3.15 and uv lock --upgrade (unblocks Dependabot security updates; move syrupy
  snapshots to __snapshots__
  ([`33d6c6f`](https://github.com/alawresz/climate_orchestrator/commit/33d6c6fa2fa94c88e58912088a6fd3ab6539e326))

### Code Style

- Align all Markdown tables to improve formatting consistency across documentation, add mdformat
  ([`d69085d`](https://github.com/alawresz/climate_orchestrator/commit/d69085dea8aff40846b9941bb3b32324eff7cd9f))

### Features

- Repair when AC drain protection's sensor is configured but unavailable
  ([`886bfa1`](https://github.com/alawresz/climate_orchestrator/commit/886bfa17257af2637bae6e4176ba2bf85ed847d1))

### Testing

- Assert coordinator-not-shutdown on failed unload (HA-version-robust)
  ([`91f096b`](https://github.com/alawresz/climate_orchestrator/commit/91f096be4007a543bcf535b85030981b68759620))

- Restore snapshot dir to snapshots/ for HA syrupy extension
  ([`fea9394`](https://github.com/alawresz/climate_orchestrator/commit/fea9394ed14bd1c76e0c34d913a9ff2cc57693b9))


## v0.32.0 (2026-06-28)

### Chores

- Bump codecov/codecov-action from 6.0.1 to 7.0.0
  ([#11](https://github.com/alawresz/climate_orchestrator/pull/11),
  [`68a4942`](https://github.com/alawresz/climate_orchestrator/commit/68a49426d94f6732c074e9bf1e68cc2663cc3998))

### Features

- Add AC drain protection config along with tests and documentation
  ([`301bdb3`](https://github.com/alawresz/climate_orchestrator/commit/301bdb3754d567c3802ae3901a0a2f88928d7dce))


## v0.31.2 (2026-06-06)

### Bug Fixes

- Clear all repairs on unload, prune removed-device entities, pin MPC diag params
  ([`bf96b8f`](https://github.com/alawresz/climate_orchestrator/commit/bf96b8f922b9268a1f6be7cc62b92782c6673ba5))


## v0.31.1 (2026-06-06)

### Bug Fixes

- Make MPC diagnostic reads safe against the executor thread
  ([`eb57905`](https://github.com/alawresz/climate_orchestrator/commit/eb579058c9a3b0dc44927d9aa6b6bcc41c3669f1))


## v0.31.0 (2026-06-06)

### Chores

- Declare platinum quality scale and cap scipy below 2.0
  ([`6b1d012`](https://github.com/alawresz/climate_orchestrator/commit/6b1d012074618e8f6a808c5cc687064ca6b2397c))

### Documentation

- Fix year typo
  ([`1d0ca7e`](https://github.com/alawresz/climate_orchestrator/commit/1d0ca7ed3c76b0b3d125cbca5faa7a96d8af9c92))

### Features

- Surface a repair when forecast preconditioning can't fetch a forecast
  ([`b57ce40`](https://github.com/alawresz/climate_orchestrator/commit/b57ce40fffe4ad454f91e10e177ba44eda4dddce))

### Refactoring

- Lazy-import scipy so non-MPC installs never load it
  ([`cbef557`](https://github.com/alawresz/climate_orchestrator/commit/cbef55760a0c2c6c62796c37327b5924ddd4524f))


## v0.30.1 (2026-06-06)

### Bug Fixes

- Clear per-device repair issues on entry unload and mode change
  ([`9c86fc8`](https://github.com/alawresz/climate_orchestrator/commit/9c86fc85a2eb12188fb937c61dbac7bb85c28b66))

### Documentation

- Fix ADR-0001 date and de-version the ADR-0006 example
  ([`8bbeaa5`](https://github.com/alawresz/climate_orchestrator/commit/8bbeaa59891b42f23c4a2828c57b23aa8a4ab92d))

- Fix internals drift (adapter/profile model, store contents, MPC equation)
  ([`0138973`](https://github.com/alawresz/climate_orchestrator/commit/0138973c2f4ad2810a7a288b0a0a627fcf8cc6dd))

### Refactoring

- Name the MPC per-step residual in one place
  ([`4959202`](https://github.com/alawresz/climate_orchestrator/commit/4959202edd34641e2c10926c77c431dff5288c26))

### Testing

- Guard that every repair key has a strings.json entry
  ([`dcd7581`](https://github.com/alawresz/climate_orchestrator/commit/dcd75812518b3958976fd29f8b9439e303a0a06e))


## v0.30.0 (2026-06-06)

### Documentation

- Add a Decisions section and backfill ADRs 0001–0007
  ([`efc233f`](https://github.com/alawresz/climate_orchestrator/commit/efc233f48dd9aa4cff21dcea4fbf6e3a167e49ed))

### Features

- Flag a TRV whose MPC model fits persistently poorly
  ([`234a206`](https://github.com/alawresz/climate_orchestrator/commit/234a206da0618cbfdbb22eac508cd7eb08018dba))

### Refactoring

- Resolve per-device behaviour through a DeviceProfile seam
  ([`ba00a87`](https://github.com/alawresz/climate_orchestrator/commit/ba00a8708a5986397885dc18c685f136fc3e79ec))


## v0.29.0 (2026-06-06)

### Chores

- **coverage**: Raise the gate to 97% and mark the import fallback
  ([`32a1369`](https://github.com/alawresz/climate_orchestrator/commit/32a13691a5968ab0ff9a77e89a34d46c4386e2f4))

### Features

- Flag AC-dependent settings that can't act on the configured hardware
  ([`eb3b7c7`](https://github.com/alawresz/climate_orchestrator/commit/eb3b7c7fd275faa5213e41f6f78861101f01b3b9))

### Testing

- Cover the window recheck timer, forecast defenses, and guard paths
  ([`12c288b`](https://github.com/alawresz/climate_orchestrator/commit/12c288bcaf046962376e2cf6ae904ceeb44081d0))


## v0.28.7 (2026-06-05)

### Bug Fixes

- Ignore a stale forecast cache instead of preconditioning on dead data
  ([`f9c0b1a`](https://github.com/alawresz/climate_orchestrator/commit/f9c0b1a24d418f2fa819bf00d5479b735f160f1d))

### Chores

- Expand ruff ruleset (bandit, pylint, pytest-style + 14 free groups) and fix findings
  ([`e3f3e91`](https://github.com/alawresz/climate_orchestrator/commit/e3f3e9168a78d97ff0c48c98a0847ebd7ce58c3e))

### Documentation

- Fix post-extraction attribution drift and clarify mutation scope
  ([`af40217`](https://github.com/alawresz/climate_orchestrator/commit/af402175b70eba105608ee70e2b7cf948752ebd3))

- Record tuning-constant rationale, test-helper preconditions, and config migration how-to
  ([`5ffa0d1`](https://github.com/alawresz/climate_orchestrator/commit/5ffa0d1e9eb601f2d38819bcb51d334605773f7d))

### Refactoring

- Add `last_maintenance` property for diagnostics and replace direct access to `_last_maintenance`
  ([`e53813a`](https://github.com/alawresz/climate_orchestrator/commit/e53813afb084d625f7a1bc91b92a750dd7503467))

- Enum membership, comprehensions, no throwaway runtime construction
  ([`0a9b8f1`](https://github.com/alawresz/climate_orchestrator/commit/0a9b8f1f97fb442d8a30a27ac42882777ba9afac))

- Extract LearnedStateStores (persistence) from the coordinator
  ([`af0332b`](https://github.com/alawresz/climate_orchestrator/commit/af0332b780994233ddc9ec370a07ffd0d087672d))

- Extract WeatherAdaptation from the coordinator
  ([`d954161`](https://github.com/alawresz/climate_orchestrator/commit/d954161e9a1a162e8631d3b02760486255660862))

- Extract WindowMonitor from the coordinator
  ([`5af3a5a`](https://github.com/alawresz/climate_orchestrator/commit/5af3a5a671e9fffe364ad37a2d7437872d56ab4f))

- **test**: Route all coordinator-internal access through helpers, enforced via SLF001
  ([`0b03c4d`](https://github.com/alawresz/climate_orchestrator/commit/0b03c4d21c129b5de9de3240eeb6cc86be87d615))


## v0.28.6 (2026-06-05)

### Bug Fixes

- Tolerate corrupt restore data (boost deadline type check, MPC drop warning)
  ([`102f4bd`](https://github.com/alawresz/climate_orchestrator/commit/102f4bd2aad4ab0b2d12edc9bce0f7e444233461))


## v0.28.5 (2026-06-05)

### Bug Fixes

- Push a failed release
  ([`16d2eb2`](https://github.com/alawresz/climate_orchestrator/commit/16d2eb23a95245076c5549c8c6f6489f0866c9f6))


## v0.28.4 (2026-06-05)

### Bug Fixes

- Handle mid-boost deselection by restoring to previous preset if available
  ([`a36329a`](https://github.com/alawresz/climate_orchestrator/commit/a36329a89424cda1784b17552da60251c3478080))

- Handle mid-boost deselection by restoring to previous preset if available
  ([`1bf1384`](https://github.com/alawresz/climate_orchestrator/commit/1bf13843c8f9955631dfdba9dffe64cdb08a3793))

### Continuous Integration

- Add backfill-releases workflow to retroactively update GitHub Releases
  ([`0b62b45`](https://github.com/alawresz/climate_orchestrator/commit/0b62b453253040078541f0eec49881a714898d33))

- Add CodeQL workflow for SAST and README badge integration
  ([`4681ad2`](https://github.com/alawresz/climate_orchestrator/commit/4681ad2df2addf86ee2afafb3bb6c038e4a93ea2))

- Add workflows for OpenSSF Scorecard and Dependabot auto-merge
  ([`7e5b892`](https://github.com/alawresz/climate_orchestrator/commit/7e5b8929558faf557f0ae78e39fb08e037be68c4))

- Auto-close tracking issues on recovery for canary workflows
  ([`9761a84`](https://github.com/alawresz/climate_orchestrator/commit/9761a8423b898d5d29a52c5cc0e541c674b2de1d))

- Enhance workflows with tighter permissions, Sigstore bundles, and SECURITY.md
  ([`aa9fd7c`](https://github.com/alawresz/climate_orchestrator/commit/aa9fd7cf74557ac4ec165a2ef9be4e089278133e))

- Exclude syrupy snapshot tests from HA floor runs, update paths
  ([`b6a8f5c`](https://github.com/alawresz/climate_orchestrator/commit/b6a8f5c3a8c8fc8d21111144989995968a103e37))

- Fix packaging process
  ([`be180e6`](https://github.com/alawresz/climate_orchestrator/commit/be180e63a65025919614da1343299c722e7c8455))

- Release via a dedicated GitHub App to pass the main ruleset
  ([`2dc94a4`](https://github.com/alawresz/climate_orchestrator/commit/2dc94a4667d4aa35f7cfc1dc6a3927bc0ac36c8e))

- Remove backfill-releases workflow as it is no longer needed
  ([`49a56bf`](https://github.com/alawresz/climate_orchestrator/commit/49a56bf8e38ee5041f968ce972647cb8b474ef32))


## v0.28.3 (2026-06-05)

### Bug Fixes

- Support the documented HA floor (2025.2) on older installs
  ([`74f378e`](https://github.com/alawresz/climate_orchestrator/commit/74f378ebd633b967efff915e0017a515ab162255))

### Continuous Integration

- Path-scoped jobs, HA floor canary, timeouts, concurrency, failure issues, actionlint
  ([`1a71122`](https://github.com/alawresz/climate_orchestrator/commit/1a71122e0cae5548c67c03c57709c2ca43ff82c2))

### Documentation

- Clarify Python version gates and their roles in dev setup
  ([`1ed279a`](https://github.com/alawresz/climate_orchestrator/commit/1ed279ad932d015fff0df7f5c300caa4949c76ab))


## v0.28.2 (2026-06-04)

### Bug Fixes

- Keep status initializing while devices are still joining after restart
  ([`19f9f82`](https://github.com/alawresz/climate_orchestrator/commit/19f9f82e073ccaf34b284c1d4131e61ab3a861bd))

### Documentation

- Sync feature tour, persistence, and entity reference with recent features
  ([`d8275bc`](https://github.com/alawresz/climate_orchestrator/commit/d8275bc0fa178d808c315d0920e2e34eff6c22a4))

### Refactoring

- Centralize refresh helper and isolate write operations in coordinator
  ([`5c23a48`](https://github.com/alawresz/climate_orchestrator/commit/5c23a489566f4ce0445e1723f07630d2638cb2ac))


## v0.28.1 (2026-06-04)

### Bug Fixes

- Missing release zip
  ([`d231d69`](https://github.com/alawresz/climate_orchestrator/commit/d231d69be199197190f6f9fe71da97de5ed41835))

### Refactoring

- Extract events, supervision, and repairs from the coordinator
  ([`311cc73`](https://github.com/alawresz/climate_orchestrator/commit/311cc730a3935e8d237876ea4fa058a7d578306b))


## v0.28.0 (2026-06-04)

### Documentation

- Unify browser-storage scope across versions for consistent cache management
  ([`e940af1`](https://github.com/alawresz/climate_orchestrator/commit/e940af1cbd52751b0772a43dcb3ff13f46734275))

### Features

- Manual-override takeover honors external device changes
  ([`8660158`](https://github.com/alawresz/climate_orchestrator/commit/866015826b7d21e2accdc9caaada845b6c1cf244))


## v0.27.0 (2026-06-04)

### Chores

- Add issue forms and PR template
  ([`34d5b3c`](https://github.com/alawresz/climate_orchestrator/commit/34d5b3c02011248d37beeb9a41c088ecebe5d9e6))

- Purge historical narration and dead DESIGN.md pointers from comments
  ([`2ed4bbf`](https://github.com/alawresz/climate_orchestrator/commit/2ed4bbf301f3d85c2c314dd6282fc39904a9f7ff))

### Continuous Integration

- Add per-page revision dates, privacy plugin, and instant navigation to docs
  ([`6059169`](https://github.com/alawresz/climate_orchestrator/commit/6059169d250c2166bb4f71f85cc635b5045c14f7))

- Expand link check to include issue/PR templates and docs-site chapters
  ([`c3073e3`](https://github.com/alawresz/climate_orchestrator/commit/c3073e3564445a2872aa75d8dc0e4c98ce147446))

### Documentation

- Clarify dry-bulb fallback when humidity sensors are missing
  ([`b9c9c22`](https://github.com/alawresz/climate_orchestrator/commit/b9c9c2280ecfb52edc42578d00f55515db0aea30))

- Version-prefix absolute docs links and fix the TRV controller anchor
  ([`741afd3`](https://github.com/alawresz/climate_orchestrator/commit/741afd3e6f45d6af172a10479c1c071fb623ec1c))

### Features

- Bus events for operational transitions with self-clearing notifications
  ([`0f466dd`](https://github.com/alawresz/climate_orchestrator/commit/0f466dd97e4e67513845f34476f3f098bc024da2))


## v0.26.0 (2026-06-04)

### Features

- Watchdog repair for devices that silently ignore commands
  ([`a5c8649`](https://github.com/alawresz/climate_orchestrator/commit/a5c8649157e255c565de389717bbe208127c563c))


## v0.25.0 (2026-06-04)

### Continuous Integration

- Publish only released docs versions
  ([`28ab1a8`](https://github.com/alawresz/climate_orchestrator/commit/28ab1a838a3d29d732ee0615ff18166cc1b1cc45))

### Features

- Boost preset with directional band push and timed auto-revert
  ([`b8b3e3c`](https://github.com/alawresz/climate_orchestrator/commit/b8b3e3ce24fd6811af6445f956c0dfd19bb907ed))


## v0.24.0 (2026-06-04)

### Features

- Configurable preset selection in the config and options flows
  ([`6dbc29e`](https://github.com/alawresz/climate_orchestrator/commit/6dbc29ebd734de63ecc69e247f8f5ea82616474f))


## v0.23.0 (2026-06-04)

### Bug Fixes

- Re-arm window recheck timer mid-grace
  ([`4513046`](https://github.com/alawresz/climate_orchestrator/commit/4513046ab6a7c867ce1c0d8cebed6bc1fddc13d1))

### Documentation

- Document docs workflow
  ([`e29dde8`](https://github.com/alawresz/climate_orchestrator/commit/e29dde87c9b4bd48a945b195325c6538c79dd43b))

### Features

- Fold per-TRV MPC diagnostics into the learning-status sensor's attributes
  ([`56d381c`](https://github.com/alawresz/climate_orchestrator/commit/56d381c9fdc2320ae9e09140af457dc1f25f19ef))


## v0.22.6 (2026-06-04)

### Bug Fixes

- Persist-limiter sync + earliest-deadline window recheck
  ([`accc2ee`](https://github.com/alawresz/climate_orchestrator/commit/accc2eebc70a76c3023eb7e6854fa64706fd66eb))

### Continuous Integration

- Dispatch versioned docs deploy from the release workflow
  ([`77f7ae3`](https://github.com/alawresz/climate_orchestrator/commit/77f7ae3d1932b8d0fbb021ab73a0241c27b4de30))

- Update GH Actions to v5 for pages artifact and deployment
  ([`965cb33`](https://github.com/alawresz/climate_orchestrator/commit/965cb33bcb598b03adf46b5ed35a1ab7c6534561))

- Weekly canary against Home Assistant pre-releases
  ([`650c2be`](https://github.com/alawresz/climate_orchestrator/commit/650c2becfc8031ad2ccc44f0e81a95eeea554220))

### Documentation

- Accuracy fixes
  ([`7ad2e82`](https://github.com/alawresz/climate_orchestrator/commit/7ad2e824469f5e449707297d8053b8ff9ea33294))

- Add debug logging setup instructions to README
  ([`4590c68`](https://github.com/alawresz/climate_orchestrator/commit/4590c68b2aecaa44e4c0adfbb56af87369a1f1fe))

- Drop third-party comparisons
  ([`097eca0`](https://github.com/alawresz/climate_orchestrator/commit/097eca0a76b020349e4c798d17f8f4b677c0da01))

- Fix comment
  ([`e2f144c`](https://github.com/alawresz/climate_orchestrator/commit/e2f144c300044380a50ca89f63204e22e0b05d5c))

- Remove DESIGN, add mkdocs + GH pages
  ([`a9b67d2`](https://github.com/alawresz/climate_orchestrator/commit/a9b67d2b4b1ae1c0ca5506ccac7bb51978c690cf))

### Testing

- Kill mutmut survivors at the MPC dt boundary and fit-rejection guard
  ([`cc30384`](https://github.com/alawresz/climate_orchestrator/commit/cc30384a2cbafed5d6296c0f25d82f54bea92199))

- Pin MPC dt-cap boundary, Kalman recovery, tail-holding
  ([`db74a9a`](https://github.com/alawresz/climate_orchestrator/commit/db74a9aeea7caf626ca40fe4a5c62ecd1e53cd95))


## v0.22.5 (2026-06-04)

### Bug Fixes

- Clamp runtime settings to declared bounds + guard maintenance clock skew
  ([`1158ce0`](https://github.com/alawresz/climate_orchestrator/commit/1158ce0502aa110f3a8edec59eec617cc54ba4b4))


## v0.22.4 (2026-06-04)

### Bug Fixes

- Survive store schema mismatches — versioned migration + downgrade discard
  ([`5fda8b5`](https://github.com/alawresz/climate_orchestrator/commit/5fda8b59a9176b0864b32e8d2c90375188126be2))


## v0.22.3 (2026-06-04)

### Bug Fixes

- Bound runtime state — store eviction, window-timer pruning, forecast cap
  ([`6926e5d`](https://github.com/alawresz/climate_orchestrator/commit/6926e5dfc008dcefbd8c39cd4950dde48398aa19))

- Rate-limit learned-state store writes
  ([`b6710ce`](https://github.com/alawresz/climate_orchestrator/commit/b6710cec10d746c1fadd286539977245e72a95eb))

### Code Style

- WEATHER obj formatting
  ([`0d15f88`](https://github.com/alawresz/climate_orchestrator/commit/0d15f884f976eba594ad032b5f7efe260da12a3d))


## v0.22.2 (2026-06-04)

### Bug Fixes

- Harden MPC numerics — fit bounds, variance ceiling, gap re-anchor, restore validation
  ([`733dba2`](https://github.com/alawresz/climate_orchestrator/commit/733dba2bec70b125add4dd23a6675405826594fc))

- Tie fire-and-forget tasks to the config entry lifecycle
  ([`1016726`](https://github.com/alawresz/climate_orchestrator/commit/1016726a02eac7b513ffac7fe4d5f7d722a55479))

### Code Style

- Predict in test_observer.py
  ([`4ffd68e`](https://github.com/alawresz/climate_orchestrator/commit/4ffd68ea03430a78152a4405d45073f7ad085103))


## v0.22.1 (2026-06-04)

### Bug Fixes

- Reject non-finite sensor values (nan/inf) in every numeric read
  ([`ea29985`](https://github.com/alawresz/climate_orchestrator/commit/ea299853e75f618bb240cd30b1dae845a49ef9b5))


## v0.22.0 (2026-06-04)

### Features

- Close quality-scale todos: translated errors, log-once outages, executor MPC, opt-in counters
  ([`b156d1d`](https://github.com/alawresz/climate_orchestrator/commit/b156d1df5653bfa4aaf59e750afdda20ad174724))

### Testing

- Simplify error raising in actuation rejection test
  ([`d07859e`](https://github.com/alawresz/climate_orchestrator/commit/d07859e46749f311913f4a94a52651ac502dd1a5))


## v0.21.0 (2026-06-04)

### Chores

- Add quality scale
  ([`34aa36a`](https://github.com/alawresz/climate_orchestrator/commit/34aa36a89b5cf0e0d46184cbb85f1b96d8b6c2aa))

### Continuous Integration

- Update HACS brands handling for HA 2026.3 local icons
  ([`9396af3`](https://github.com/alawresz/climate_orchestrator/commit/9396af337e2a0fc05ec2fc27bb0cdd9b6ac6ece4))

### Features

- Add entry removal cleanup and optimize entity updates
  ([`782ff06`](https://github.com/alawresz/climate_orchestrator/commit/782ff066c6af0be068dd1aa15b41f225fbb782a3))

### Refactoring

- Shared state helpers, settings snapshot, pure runtime stats
  ([`44f0886`](https://github.com/alawresz/climate_orchestrator/commit/44f0886daa526e9ea5e50c52171328886a05f24c))

### Testing

- Kill runtime-stats, Kalman, and preconditioning mutation survivors
  ([`6304f01`](https://github.com/alawresz/climate_orchestrator/commit/6304f013c01b5e1a711b809648333beddf322725))


## v0.20.3 (2026-06-04)

### Bug Fixes

- Discard corrupt persisted MPC state instead of failing setup
  ([`a694dec`](https://github.com/alawresz/climate_orchestrator/commit/a694dece212409993cc7742afd4affb07108349b))

### Continuous Integration

- Add config entry migration scaffolding, weekly link checks, and coverage component split
  ([`411aa43`](https://github.com/alawresz/climate_orchestrator/commit/411aa43a03f3731f66f7ac4b0260eaa26b4c3aa0))

### Refactoring

- **tests**: Centralize TRV setup and calibration helpers in `tests/ha/helpers.py`
  ([`f19b1ed`](https://github.com/alawresz/climate_orchestrator/commit/f19b1edab7390be6628b41e411529ed593e176f4))


## v0.20.2 (2026-06-04)

### Bug Fixes

- Upload HACS zip asset to release
  ([`1eb0f9a`](https://github.com/alawresz/climate_orchestrator/commit/1eb0f9aeb5eef2bda4846d3057e939f921d740bb))


## v0.20.1 (2026-06-04)

### Bug Fixes

- Ship and attest the HACS zip asset
  ([`ff1c584`](https://github.com/alawresz/climate_orchestrator/commit/ff1c584e8a60246a02eed6e1358eb8815c7cd1b7))

### Continuous Integration

- SHA-pin actions, guard release trigger, lint workflows with zizmor
  ([`68dbe73`](https://github.com/alawresz/climate_orchestrator/commit/68dbe73674db3503e4d4f223fc8610b4a7d3c395))


## v0.20.0 (2026-06-03)

### Features

- **mpc**: Wire the Kalman observer into valve planning
  ([`3593556`](https://github.com/alawresz/climate_orchestrator/commit/3593556a89290d419736f74315dfc9111516b9c4))


## v0.19.2 (2026-06-03)

### Bug Fixes

- Extract per-device control flow and cycle context, compute AC bias error against the current
  cycle's home average
  ([`aa54c52`](https://github.com/alawresz/climate_orchestrator/commit/aa54c5213a89b780c981663c83f62c2867e0cb51))

### Continuous Integration

- Remove advisory "continue-on-error" for hassfest validation
  ([`8726404`](https://github.com/alawresz/climate_orchestrator/commit/8726404647f3816713fa908f678a3a0921cf1783))


## v0.19.1 (2026-06-03)

### Bug Fixes

- Update strings.json, enforce strings.json and translations/en.json sync in pre-commit and CI
  ([`abb4b39`](https://github.com/alawresz/climate_orchestrator/commit/abb4b390b72b46763e45ed4bcd392c7f1a5aa2c6))

### Continuous Integration

- Restore changelog generation under PSR v10
  ([`687910a`](https://github.com/alawresz/climate_orchestrator/commit/687910abbd8e48850bfd36550fa9e1f48270ccca))

- Upload JUnit test results to Codecov Test Analytics
  ([`27eba16`](https://github.com/alawresz/climate_orchestrator/commit/27eba1626825488528c2e4521aafbbd66a543129))


## v0.19.0 (2026-06-03)

### Features

- Home-average trigger switch for fully independent rooms
  ([`86903ea`](https://github.com/alawresz/climate_orchestrator/commit/86903eaaf714a883da951b9ff1e07f6e66f068b6))


## v0.18.0 (2026-06-03)

### Features

- User-provided whole-home average sensors with source diagnostic
  ([`f203b30`](https://github.com/alawresz/climate_orchestrator/commit/f203b3005d366430b65ba6dcc8907c7616f5a69d))


## v0.17.0 (2026-06-03)

### Features

- Raise a repair when the control cycle keeps failing
  ([`10434fb`](https://github.com/alawresz/climate_orchestrator/commit/10434fb94418e23642e0133a51d09e385668c075))


## v0.16.0 (2026-06-03)

### Bug Fixes

- Improve forecast parsing robustness by adding strict type checks for response handling
  ([`9f17e24`](https://github.com/alawresz/climate_orchestrator/commit/9f17e24f4b2da892a7eb8af1e4e07cf7f8a5c8b0))

### Documentation

- Update README and DESIGN.md to reflect recent features and improvements
  ([`a9d41cc`](https://github.com/alawresz/climate_orchestrator/commit/a9d41cc5e53222c441d57e7d32b2c8b51f43ff55))

### Features

- Add forecast-based preconditioning for MPC TRVs; fetch hourly weather forecasts and optimize valve
  control to pre-heat ahead of cold spells; update docs, settings, and tests
  ([`7e1da1a`](https://github.com/alawresz/climate_orchestrator/commit/7e1da1ac6ba24bf69f7101e3e21e8c09a557767b))


## v0.15.0 (2026-06-03)

### Features

- Rename "Adaptive comfort" to "Adaptive cooling comfort" and "Adaptive AC bias" to "Self-tuning AC
  bias" for clarity; update references, docs, and tests accordingly
  ([`a764205`](https://github.com/alawresz/climate_orchestrator/commit/a764205ff38fa437b6a18abad329702d7e657e95))


## v0.14.0 (2026-06-03)

### Features

- Introduce per-area comfort band offsets for localized temperature adjustments and improved
  flexibility
  ([`262f5f0`](https://github.com/alawresz/climate_orchestrator/commit/262f5f01cdad7799522414045d6415cbcd55fa3d))


## v0.13.0 (2026-06-03)

### Features

- Replace degraded binary sensor with status sensor for improved diagnostics and post-restart
  warm-up handling
  ([`129b962`](https://github.com/alawresz/climate_orchestrator/commit/129b962497fc951fe5a745c456b449a04ba038b1))

### Testing

- Add unit tests for status sensor behavior during warm-up and degraded states
  ([`7651565`](https://github.com/alawresz/climate_orchestrator/commit/76515654c567b092888c2aa25afa93b713e7fb0c))


## v0.12.1 (2026-06-03)

### Bug Fixes

- Ac heating assist to allow AC-only setups to function as full heat/cool thermostats, update docs
  and tests accordingly
  ([`b325422`](https://github.com/alawresz/climate_orchestrator/commit/b325422efa656cf5940b58248ccf4d90d0780745))


## v0.12.0 (2026-06-03)

### Chores

- Update ruff version, fix type hint, and adjust manifest formatting
  ([`07b2fcd`](https://github.com/alawresz/climate_orchestrator/commit/07b2fcd42e8848985e64fe62658df2f182fd3b19))

### Continuous Integration

- Add semantic release configuration and workflow for automated versioning
  ([`c954162`](https://github.com/alawresz/climate_orchestrator/commit/c95416296f18c424b2ef8b77583600e406abd633))

- Integrate Codecov for test coverage reporting and add badge to README
  ([`19beacb`](https://github.com/alawresz/climate_orchestrator/commit/19beacb438781208fb49208692c03285ebda8b3a))

- Update workflow to set read-only permissions
  ([`db8776e`](https://github.com/alawresz/climate_orchestrator/commit/db8776ea49a607d1f55175db6ef489bb2fcd6bb9))

### Documentation

- Add badges to README and improve HACS installation instructions
  ([`534f991`](https://github.com/alawresz/climate_orchestrator/commit/534f9914e4341c6a1d05c52cd0500936b61bb6b7))

### Features

- Throttle AC setpoint writes to reduce radio spam and improve efficiency
  ([`8af8c95`](https://github.com/alawresz/climate_orchestrator/commit/8af8c95e7ef647015b43433d379b97f77daac51c))


## v0.11.0 (2026-06-03)

### Chores

- Init commit
  ([`3407209`](https://github.com/alawresz/climate_orchestrator/commit/3407209458ae2c75082db43e266e620cd1e0a77c))
