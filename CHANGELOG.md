# CHANGELOG

<!-- version list -->

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
