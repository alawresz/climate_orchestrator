# CHANGELOG

<!-- version list -->

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
