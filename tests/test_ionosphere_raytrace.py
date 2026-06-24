"""Optional-layer tests — solar geometry (dep-free), parametric ionosphere,
and the raytrace wrapper's graceful-absent path."""
from datetime import datetime, timezone

import pytest

from hamsci_dsp.ionosphere import (
    ionosphere_state,
    solar_position,
    solar_zenith_angle,
)
from hamsci_dsp.raytrace import RaytraceEngine


def test_sun_high_at_local_noon_equator_equinox():
    # ~equinox, solar noon at lon 0 → sun nearly overhead at the equator.
    dt = datetime(2026, 3, 20, 12, 0, 0, tzinfo=timezone.utc)
    az, el = solar_position(dt, 0.0, 0.0)
    assert el > 80.0
    assert solar_zenith_angle(dt, 0.0, 0.0) < 10.0


def test_sun_below_horizon_at_local_midnight():
    dt = datetime(2026, 3, 20, 0, 0, 0, tzinfo=timezone.utc)
    _, el = solar_position(dt, 0.0, 0.0)
    assert el < 0.0                          # night → zenith > 90
    assert solar_zenith_angle(dt, 0.0, 0.0) > 90.0


def test_parametric_ionosphere_day_vs_night():
    lat, lon = 38.94, -92.13
    day = ionosphere_state(datetime(2026, 6, 24, 18, 0, tzinfo=timezone.utc), lat, lon)
    night = ionosphere_state(datetime(2026, 6, 24, 6, 0, tzinfo=timezone.utc), lat, lon)
    # tier is "iri" if iri2020 is installed, else "parametric" — either way
    # daytime foF2 should exceed night-time foF2.
    assert day.fof2_mhz > night.fof2_mhz
    assert day.tier in ("iri", "parametric")


def test_raytrace_absent_is_graceful():
    eng = RaytraceEngine()
    # PHaRLAP/PyLAP not installed in this environment.
    if not eng.is_available():
        assert eng.compute_modes() == []
    else:                                    # pragma: no cover
        pytest.skip("pylap present; live trace not exercised here")
