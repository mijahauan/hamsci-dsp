"""Solar position / zenith — NOAA solar-calculator algorithm.

Extracted (math-identical) from hf-timestd ``core/solar_zenith_calculator.py``.
Dependency-free (stdlib ``math``); useful for organising propagation products by
local solar time / grayline and for the parametric ionosphere fallback.
"""
from __future__ import annotations

import math
from datetime import datetime
from typing import Tuple


def solar_position(dt: datetime, lat: float, lon: float) -> Tuple[float, float]:
    """Solar (azimuth, elevation) in degrees for a UTC time and location.

    lon is positive-East.  Based on the NOAA solar calculator.
    """
    a = (14 - dt.month) // 12
    y = dt.year + 4800 - a
    m = dt.month + 12 * a - 3
    jd = dt.day + (153 * m + 2) // 5 + 365 * y + y // 4 - y // 100 + y // 400 - 32045
    jd = jd + (dt.hour - 12) / 24 + dt.minute / 1440 + dt.second / 86400

    t = (jd - 2451545.0) / 36525.0
    L0 = (280.46646 + t * (36000.76983 + t * 0.0003032)) % 360
    M = 357.52911 + t * (35999.05029 - 0.0001537 * t)
    M_rad = math.radians(M)
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    C = (math.sin(M_rad) * (1.914602 - t * (0.004817 + 0.000014 * t)) +
         math.sin(2 * M_rad) * (0.019993 - 0.000101 * t) +
         math.sin(3 * M_rad) * 0.000289)
    sun_lon = L0 + C
    omega = 125.04 - 1934.136 * t
    apparent_lon = sun_lon - 0.00569 - 0.00478 * math.sin(math.radians(omega))
    obliq_mean = 23 + (26 + (21.448 - t * (46.815 + t * (0.00059 - t * 0.001813))) / 60) / 60
    obliq_corr = obliq_mean + 0.00256 * math.cos(math.radians(omega))
    obliq_corr_rad = math.radians(obliq_corr)
    sin_decl = math.sin(obliq_corr_rad) * math.sin(math.radians(apparent_lon))
    decl = math.degrees(math.asin(sin_decl))
    decl_rad = math.radians(decl)

    var_y = math.tan(obliq_corr_rad / 2) ** 2
    L0_rad = math.radians(L0)
    eq_time = 4 * math.degrees(
        var_y * math.sin(2 * L0_rad) -
        2 * e * math.sin(M_rad) +
        4 * e * var_y * math.sin(M_rad) * math.cos(2 * L0_rad) -
        0.5 * var_y * var_y * math.sin(4 * L0_rad) -
        1.25 * e * e * math.sin(2 * M_rad))

    time_offset = eq_time + 4 * lon
    true_solar_time = (dt.hour * 60 + dt.minute + dt.second / 60 + time_offset) % 1440
    if true_solar_time < 0:
        hour_angle = true_solar_time / 4 + 180
    else:
        hour_angle = true_solar_time / 4 - 180
    hour_angle_rad = math.radians(hour_angle)

    lat_rad = math.radians(lat)
    cos_zenith = (math.sin(lat_rad) * math.sin(decl_rad) +
                  math.cos(lat_rad) * math.cos(decl_rad) * math.cos(hour_angle_rad))
    cos_zenith = max(-1.0, min(1.0, cos_zenith))
    zenith = math.degrees(math.acos(cos_zenith))
    elevation = 90.0 - zenith

    sin_zenith = math.sin(math.radians(zenith))
    if abs(sin_zenith) < 1e-9:
        azimuth = 0.0
    elif hour_angle > 0:
        azimuth = (math.degrees(math.acos(max(-1.0, min(1.0,
                   ((math.sin(lat_rad) * cos_zenith) - math.sin(decl_rad)) /
                   (math.cos(lat_rad) * sin_zenith))))) + 180) % 360
    else:
        azimuth = (540 - math.degrees(math.acos(max(-1.0, min(1.0,
                   ((math.sin(lat_rad) * cos_zenith) - math.sin(decl_rad)) /
                   (math.cos(lat_rad) * sin_zenith)))))) % 360
    return azimuth, elevation


def solar_zenith_angle(dt: datetime, lat: float, lon: float) -> float:
    """Solar zenith angle (deg); 0 = overhead, 90 = horizon, >90 = night."""
    _, elevation = solar_position(dt, lat, lon)
    return 90.0 - elevation
