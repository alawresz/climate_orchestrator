"""Shared test constants.

The hass fixtures live in ``tests/ha/conftest.py`` so that the pure unit tests
under ``tests/unit/`` don't pull in the Home Assistant test harness — which also
lets mutation testing target ``tests/unit/`` alone (see ``[tool.mutmut]``).
"""

from __future__ import annotations

TRV_ENTITY = "climate.trv_1"
AC_ENTITY = "climate.ac"
AREA_TEMP_SENSOR = "sensor.living_temperature"
AREA_HUMIDITY_SENSOR = "sensor.living_humidity"
