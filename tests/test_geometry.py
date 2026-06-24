"""Geometry tests — geographiclib parity, agreement with the old haversine,
reflection geometry, and Maidenhead round-trips."""
import math

import pytest

from hamsci_dsp import geometry as G


def _haversine_km(lat1, lon1, lat2, lon2):
    """The spherical formula the clients used, for a <0.5% agreement check."""
    R = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * R * math.asin(min(1.0, math.sqrt(a)))


# Fulton, MO (EM38ww) and Fort Hays, KS (fhe)
RX = (38.94, -92.13)
FHE = (38.85877, -99.38843)


def test_great_circle_matches_haversine_within_half_percent():
    d_geo = G.great_circle_km(*RX, *FHE)
    d_hav = _haversine_km(*RX, *FHE)
    assert abs(d_geo - d_hav) / d_hav < 0.005
    assert 600 < d_geo < 650          # ~628 km, Fort Hays from central MO


def test_bearing_is_westerly_to_fort_hays():
    b = G.bearing_deg(*RX, *FHE)
    assert 250 < b < 290              # roughly west / WNW


def test_midpoint_between_is_between():
    mlat, mlon = G.midpoint(*RX, *FHE)
    assert min(RX[0], FHE[0]) - 0.5 <= mlat <= max(RX[0], FHE[0]) + 0.5
    assert FHE[1] < mlon < RX[1]


def test_destination_roundtrips_with_distance_and_bearing():
    d = G.great_circle_km(*RX, *FHE)
    b = G.bearing_deg(*RX, *FHE)
    lat2, lon2 = G.destination(*RX, b, d)
    assert abs(lat2 - FHE[0]) < 1e-3
    assert abs(lon2 - FHE[1]) < 1e-3


def test_elevation_angle_decreases_with_distance():
    near = G.elevation_angle_deg(500.0, 300.0)
    far = G.elevation_angle_deg(2000.0, 300.0)
    assert near > far
    assert 0.0 < far < near < 90.0


def test_hop_geometry_spherical_path_inverts_via_height_from_path():
    # Spherical law-of-cosines model: height_from_path must recover the height
    # used to build the path (forward/inverse round-trip).
    D, h, N = 1500.0, 300.0, 1
    hg = G.hop_geometry(D, h, N)
    assert hg.path_length_km > D
    assert hg.height_km == h and hg.reflection_height_km == h
    recovered = G.height_from_path(hg.path_length_km, D, N)
    assert recovered is not None and abs(recovered - h) < 1e-6
    # Multi-hop round-trip too.
    hg4 = G.hop_geometry(6000.0, 280.0, 3)
    assert abs(G.height_from_path(hg4.path_length_km, 6000.0, 3) - 280.0) < 1e-6


def test_hop_geometry_geometric_delay_and_helpers():
    hg = G.hop_geometry(2000.0, 300.0, 1)
    # geometric delay = slant path / c (km per ms)
    assert hg.geometric_delay_ms == pytest.approx(hg.path_length_km / 299.792458)
    # feasibility helpers
    assert G.n_hops_for_distance(1500.0, 300.0) == 1
    assert G.n_hops_for_distance(G.max_single_hop_distance_km(300.0) * 2.5, 300.0) >= 3


def test_maidenhead_roundtrip():
    lat, lon = G.grid_to_latlon("EM38ww")
    assert 38.5 < lat < 39.5 and -92.5 < lon < -91.5
    assert G.latlon_to_grid(lat, lon, precision=6) == "EM38ww"


def test_grid_requires_min_length():
    with pytest.raises(ValueError):
        G.grid_to_latlon("EM3")
