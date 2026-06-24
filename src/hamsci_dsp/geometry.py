"""Geodesy + path geometry — one tested implementation for the whole suite.

Great-circle distance / bearing / midpoint / direct were reimplemented 19+ times
across the clients (hf-timestd alone had ~17 copies), plus wspr-recorder's inline
Vincenty.  This module is the single home, backed by **geographiclib** (Karney's
geodesics on the WGS-84 ellipsoid — the reference standard) so results are
accurate and consistent everywhere.

Also provides Maidenhead grid <-> lat/lon and the spherical-Earth reflection
geometry (elevation angle, slant path) used by the oblique-sounding inversion.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Tuple

from geographiclib.geodesic import Geodesic

from hamsci_dsp.constants import R_EARTH_KM

_WGS84 = Geodesic.WGS84


# --------------------------------------------------------------------------
# Geodesics (ellipsoidal, via geographiclib)
# --------------------------------------------------------------------------

def great_circle_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Geodesic (WGS-84) distance between two points, in km."""
    return _WGS84.Inverse(lat1, lon1, lat2, lon2)["s12"] / 1000.0


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Initial (forward) azimuth from point 1 toward point 2, degrees [0, 360)."""
    return _WGS84.Inverse(lat1, lon1, lat2, lon2)["azi1"] % 360.0


def midpoint(lat1: float, lon1: float, lat2: float, lon2: float) -> Tuple[float, float]:
    """Geodesic midpoint (the path's reflection sub-point for a 1-hop path)."""
    line = _WGS84.InverseLine(lat1, lon1, lat2, lon2)
    pos = line.Position(line.s13 / 2.0)
    return pos["lat2"], pos["lon2"]


def destination(lat: float, lon: float, bearing: float, distance_km: float
                ) -> Tuple[float, float]:
    """Point reached from (lat, lon) on ``bearing`` after ``distance_km``."""
    pos = _WGS84.Direct(lat, lon, bearing % 360.0, distance_km * 1000.0)
    return pos["lat2"], pos["lon2"]


# --------------------------------------------------------------------------
# Reflection geometry (spherical Earth) — for oblique-incidence sounding
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class HopGeometry:
    n_hops: int
    ground_distance_km: float
    reflection_height_km: float
    path_length_km: float          # total slant group path
    elevation_deg: float           # take-off elevation above horizon


def elevation_angle_deg(ground_distance_km: float, reflection_height_km: float,
                        n_hops: int = 1) -> float:
    """Take-off elevation angle for an ``n_hops`` reflection at a given virtual
    height, on a spherical Earth.

    Per-hop half-ground-angle ``gamma = (d/2)/Re`` with ``d = D/N``; the
    elevation is ``atan2(cos(gamma) - Re/(Re+h), sin(gamma))``.
    """
    if n_hops < 1:
        raise ValueError(f"n_hops must be >= 1; got {n_hops}")
    d = ground_distance_km / n_hops
    gamma = (d / 2.0) / R_EARTH_KM
    rp = R_EARTH_KM + reflection_height_km
    return math.degrees(math.atan2(
        math.cos(gamma) - R_EARTH_KM / rp, math.sin(gamma)))


def hop_geometry(ground_distance_km: float, reflection_height_km: float,
                 n_hops: int = 1) -> HopGeometry:
    """Slant group path + elevation for an ``n_hops`` mirror-model reflection.

    Flat-segment slant per hop = ``2·sqrt((D/2N)² + h²)`` summed over N hops,
    i.e. total ``P = sqrt(D² + (2 N h)²)`` — the inverse of the codar virtual-
    height relation ``h = sqrt(P² - D²)/(2N)``.
    """
    path = math.sqrt(ground_distance_km ** 2
                     + (2.0 * n_hops * reflection_height_km) ** 2)
    return HopGeometry(
        n_hops=n_hops,
        ground_distance_km=ground_distance_km,
        reflection_height_km=reflection_height_km,
        path_length_km=path,
        elevation_deg=elevation_angle_deg(ground_distance_km,
                                          reflection_height_km, n_hops),
    )


# --------------------------------------------------------------------------
# Maidenhead grid locator
# --------------------------------------------------------------------------

def grid_to_latlon(grid: str) -> Tuple[float, float]:
    """Maidenhead locator (4 or 6 chars) -> (lat, lon) at the square centre."""
    g = grid.strip()
    if len(g) < 4:
        raise ValueError(f"grid must be >= 4 chars; got {grid!r}")
    g = g[:6]
    lon = (ord(g[0].upper()) - ord("A")) * 20.0 - 180.0
    lat = (ord(g[1].upper()) - ord("A")) * 10.0 - 90.0
    lon += int(g[2]) * 2.0
    lat += int(g[3]) * 1.0
    if len(g) >= 6:
        lon += (ord(g[4].upper()) - ord("A")) * (2.0 / 24.0)
        lat += (ord(g[5].upper()) - ord("A")) * (1.0 / 24.0)
        lon += (2.0 / 24.0) / 2.0          # centre of the subsquare
        lat += (1.0 / 24.0) / 2.0
    else:
        lon += 1.0                          # centre of the 2°x1° square
        lat += 0.5
    return lat, lon


def latlon_to_grid(lat: float, lon: float, precision: int = 6) -> str:
    """(lat, lon) -> Maidenhead locator (precision 4 or 6)."""
    if precision not in (4, 6):
        raise ValueError("precision must be 4 or 6")
    lon += 180.0
    lat += 90.0
    out = []
    out.append(chr(ord("A") + int(lon // 20)))
    out.append(chr(ord("A") + int(lat // 10)))
    out.append(str(int((lon % 20) // 2)))
    out.append(str(int((lat % 10) // 1)))
    if precision == 6:
        out.append(chr(ord("a") + int((lon % 2) / (2.0 / 24.0))))
        out.append(chr(ord("a") + int((lat % 1) / (1.0 / 24.0))))
    return "".join(out)
