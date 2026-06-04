"""Shared test constants.

The hass fixtures live in ``tests/ha/conftest.py`` so that the pure unit tests
under ``tests/unit/`` don't pull in the Home Assistant test harness — which also
lets mutation testing target ``tests/unit/`` alone (see ``[tool.mutmut]``).
"""

from __future__ import annotations

import os

from hypothesis import settings

# CI runners are noisy neighbours: the default 200 ms deadline is the classic
# source of flaky-only-in-CI property tests. The profile is opt-in via
# HYPOTHESIS_PROFILE=ci (set in ci.yml); local runs keep the strict default.
settings.register_profile("ci", deadline=None)
settings.load_profile(os.environ.get("HYPOTHESIS_PROFILE", "default"))

TRV_ENTITY = "climate.trv_1"
AC_ENTITY = "climate.ac"
AREA_TEMP_SENSOR = "sensor.living_temperature"
AREA_HUMIDITY_SENSOR = "sensor.living_humidity"
