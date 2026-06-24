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
from typing import Optional, Tuple

from geographiclib.geodesic import Geodesic

from hamsci_dsp.constants import C_KM_MS, R_EARTH_KM

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
#
# One ionospheric hop is the triangle (Earth centre C, ground point G,
# reflection point P): G on the surface at geocentric radius R, P at radius
# r_p = R + h above the hop midpoint.  The hop's ground arc subtends a central
# angle theta = d_hop/R; each leg (G->P) spans the half-hop angle gamma =
# theta/2.  Law of cosines for one leg's slant range:
#
#     slant^2 = R^2 + r_p^2 - 2*R*r_p*cos(gamma)
#
# and the take-off elevation is atan2(r_p*cos(gamma) - R, r_p*sin(gamma)).
# Both reduce to the flat-Earth triangle as gamma -> 0.  This spherical model
# (the hf-timestd "single source of truth", review item S2) replaces the older
# flat-segment approximation; for a 7000 km path the divergence is several
# percent (tens of ms of group delay).  Davies, K. (1990) "Ionospheric Radio"
# IEE EM Waves Series 31, §6.  The flat-segment codar virtual-height relation
# (h = sqrt(P^2-D^2)/(2N)) lives separately in propagation.oblique.


@dataclass(frozen=True)
class HopGeometry:
    """Spherical-Earth geometry of an N-hop HF skywave path."""

    n_hops: int                    # number of ionospheric reflections (>= 1)
    ground_distance_km: float      # total great-circle ground distance
    height_km: float               # reflection-layer height
    path_length_km: float          # total slant path, all hops, up + down
    elevation_deg: float           # launch / arrival elevation angle
    slant_per_leg_km: float        # one up-or-down leg of a single hop
    central_angle_rad: float       # full per-hop ground-arc central angle

    @property
    def reflection_height_km(self) -> float:
        """Alias for :attr:`height_km` — the reflection-layer height (km)."""
        return self.height_km

    @property
    def geometric_delay_ms(self) -> float:
        """Vacuum (free-space) propagation delay over the slant path."""
        return self.path_length_km / C_KM_MS


def elevation_angle_deg(ground_distance_km: float, reflection_height_km: float,
                        n_hops: int = 1,
                        earth_radius_km: float = R_EARTH_KM) -> float:
    """Take-off elevation angle for an ``n_hops`` reflection at a given virtual
    height, on a spherical Earth.

    Per-hop half-ground-angle ``gamma = (d/2)/Re`` with ``d = D/N``; the
    elevation is ``atan2(cos(gamma) - Re/(Re+h), sin(gamma))``.
    """
    if n_hops < 1:
        raise ValueError(f"n_hops must be >= 1; got {n_hops}")
    d = ground_distance_km / n_hops
    gamma = (d / 2.0) / earth_radius_km
    rp = earth_radius_km + reflection_height_km
    return math.degrees(math.atan2(
        math.cos(gamma) - earth_radius_km / rp, math.sin(gamma)))


def max_single_hop_distance_km(height_km: float,
                               earth_radius_km: float = R_EARTH_KM) -> float:
    """Largest ground distance reachable in one hop (tangent-ray limit).

    Twice the tangent-ray slant range ``sqrt(2*R*h + h^2)``; callers apply
    their own feasibility margin.
    """
    return 2.0 * math.sqrt(2.0 * earth_radius_km * height_km + height_km ** 2)


def n_hops_for_distance(ground_distance_km: float, height_km: float,
                        earth_radius_km: float = R_EARTH_KM) -> int:
    """Minimum number of hops needed to span ``ground_distance_km`` (always
    ``>= 1``). The ground-wave (no-hop) case is left to the caller."""
    max_1hop = max_single_hop_distance_km(height_km, earth_radius_km)
    if ground_distance_km <= max_1hop:
        return 1
    return max(2, int(math.ceil(ground_distance_km / max_1hop)))


def hop_geometry(ground_distance_km: float, reflection_height_km: float,
                 n_hops: int = 1,
                 earth_radius_km: float = R_EARTH_KM) -> HopGeometry:
    """Spherical-Earth law-of-cosines geometry of an N-hop skywave path.

    Total slant path is ``N·2·slant`` with the per-leg slant from the law of
    cosines above; the launch/arrival elevation comes from
    :func:`elevation_angle_deg`.  Raises ``ValueError`` for ``n_hops < 1`` or
    negative distances.
    """
    if n_hops < 1:
        raise ValueError(f"n_hops must be >= 1, got {n_hops}")
    if ground_distance_km < 0 or reflection_height_km < 0:
        raise ValueError(
            f"distances must be non-negative "
            f"(ground={ground_distance_km}, height={reflection_height_km})")

    R = earth_radius_km
    r_p = R + reflection_height_km
    hop_ground_km = ground_distance_km / n_hops
    theta = hop_ground_km / R              # per-hop ground-arc central angle
    gamma = theta / 2.0                    # half-hop: ground point -> reflection

    slant_sq = R ** 2 + r_p ** 2 - 2.0 * R * r_p * math.cos(gamma)
    slant = math.sqrt(max(0.0, slant_sq))
    path_length_km = n_hops * 2.0 * slant

    return HopGeometry(
        n_hops=n_hops,
        ground_distance_km=ground_distance_km,
        height_km=reflection_height_km,
        path_length_km=path_length_km,
        elevation_deg=elevation_angle_deg(ground_distance_km,
                                          reflection_height_km, n_hops,
                                          earth_radius_km),
        slant_per_leg_km=slant,
        central_angle_rad=theta,
    )


def height_from_path(path_length_km: float, ground_distance_km: float,
                     n_hops: int,
                     earth_radius_km: float = R_EARTH_KM) -> Optional[float]:
    """Inverse of :func:`hop_geometry`: reflection height from an observed path.

    Solves the law-of-cosines leg equation for ``r_p`` (taking the physical
    ``+`` root) and returns ``r_p - R``.  Returns ``None`` when the path is too
    short to close the triangle for this ground distance and hop count
    (discriminant < 0) or the implied height is negative.
    """
    if n_hops < 1 or path_length_km <= 0 or ground_distance_km < 0:
        return None

    R = earth_radius_km
    slant = path_length_km / (2.0 * n_hops)
    gamma = ground_distance_km / (2.0 * R * n_hops)

    discriminant = slant ** 2 - (R * math.sin(gamma)) ** 2
    if discriminant < 0:
        return None

    r_p = R * math.cos(gamma) + math.sqrt(discriminant)
    height_km = r_p - R
    if height_km < 0:
        return None
    return height_km


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
