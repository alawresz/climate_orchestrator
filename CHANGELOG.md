# CHANGELOG


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
