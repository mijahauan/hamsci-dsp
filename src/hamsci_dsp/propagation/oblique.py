"""Oblique-incidence sounding inversion — group path → ionospheric quantities.

The mirror-model virtual-height / equivalent-vertical-frequency inversion and
its uncertainty propagation are taken verbatim (math-identical) from
codar-sounder ``core/invert.py`` (Kaeppler et al. 2022, Eqs. 10/11/13/14,
multi-hop generalised).  The slant↔vertical TEC obliquity factor is from
hf-timestd ``core/tec_geometry.py``.  Together they let any client turn a
measured group delay along a known TX→RX path into reflection height, the
supportable (equivalent vertical) frequency, and an obliquity mapping.
"""
from __future__ import annotations

import math
from typing import Tuple

from hamsci_dsp.constants import C_M_S, K_TEC, R_EARTH_KM, TECU

# Ionospheric-layer altitude bands (Davies, *Ionospheric Radio* 1990 / CCIR).
_LAYER_BOUNDARIES_KM = {
    "below_E":    (None,  90.0),
    "E":          (90.0, 140.0),
    "F1":         (140.0, 220.0),
    "F2":         (220.0, 500.0),
    "F2_extreme": (500.0,  None),
}

DEFAULT_IONO_HEIGHT_KM = 350.0
MAX_OBLIQUITY_FACTOR = 10.0


def classify_layer(virtual_height_km: float) -> str:
    """Coarse ionospheric layer label from a virtual height (km)."""
    if not math.isfinite(virtual_height_km):
        return "unknown"
    for label, (lo, hi) in _LAYER_BOUNDARIES_KM.items():
        if (lo is None or virtual_height_km >= lo) and (
                hi is None or virtual_height_km < hi):
            return label
    return "unknown"


def virtual_height_km(group_range_km: float, ground_distance_km: float,
                      n_hops: int = 1) -> float:
    """Mirror-model virtual height: ``h = sqrt(P^2 - D^2) / (2N)`` (Kaeppler Eq.10)."""
    if n_hops < 1:
        raise ValueError(f"n_hops must be >= 1; got {n_hops}")
    if group_range_km <= ground_distance_km:
        raise ValueError(
            f"group_range_km ({group_range_km}) must exceed ground_distance_km "
            f"({ground_distance_km}) for a real solution")
    return math.sqrt(group_range_km ** 2 - ground_distance_km ** 2) / (2.0 * n_hops)


def equivalent_vertical_freq_mhz(oblique_freq_mhz: float, group_range_km: float,
                                 ground_distance_km: float) -> float:
    """Secant-law equivalent vertical frequency: ``fv = fo*sqrt(P^2-D^2)/P`` (Eq.11)."""
    if group_range_km <= ground_distance_km:
        raise ValueError("group_range_km must exceed ground_distance_km")
    cos_phi = math.sqrt(group_range_km ** 2 - ground_distance_km ** 2) / group_range_km
    return oblique_freq_mhz * cos_phi


def takeoff_zenith_deg(group_range_km: float, ground_distance_km: float) -> float:
    """Take-off zenith angle phi (deg) from ``sin(phi) = D/P``."""
    if group_range_km <= 0:
        raise ValueError(f"group_range_km must be > 0; got {group_range_km}")
    return math.degrees(math.asin(min(1.0, ground_distance_km / group_range_km)))


def virtual_height_uncertainty_km(group_range_km: float, ground_distance_km: float,
                                  group_range_uncertainty_km: float,
                                  ground_distance_uncertainty_km: float = 0.0,
                                  n_hops: int = 1) -> float:
    """Propagated virtual-height uncertainty (Kaeppler Eq.13, multi-hop)."""
    if n_hops < 1:
        raise ValueError(f"n_hops must be >= 1; got {n_hops}")
    h = virtual_height_km(group_range_km, ground_distance_km, n_hops=n_hops)
    if h == 0:
        return 0.0
    inner = (group_range_uncertainty_km ** 2
             - (ground_distance_km / group_range_km) ** 2
             * ground_distance_uncertainty_km ** 2)
    if inner < 0:
        inner = group_range_uncertainty_km ** 2
    return (group_range_km / (4.0 * n_hops ** 2 * h)) * math.sqrt(inner)


def equivalent_vertical_freq_uncertainty_mhz(oblique_freq_mhz: float,
                                             group_range_km: float,
                                             ground_distance_km: float,
                                             group_range_uncertainty_km: float
                                             ) -> float:
    """Propagated equivalent-vertical-frequency uncertainty (Kaeppler Eq.14)."""
    if group_range_km <= ground_distance_km:
        raise ValueError("group_range_km must exceed ground_distance_km")
    return (oblique_freq_mhz * ground_distance_km ** 2 * group_range_uncertainty_km
            / (group_range_km ** 2
               * math.sqrt(group_range_km ** 2 - ground_distance_km ** 2)))


# --------------------------------------------------------------------------
# MUF + slant/vertical obliquity
# --------------------------------------------------------------------------

def oblique_muf_mhz(critical_freq_mhz: float, group_range_km: float,
                    ground_distance_km: float) -> float:
    """Path MUF from the secant law: ``MUF = foF2 / cos(phi) = foF2 * P/sqrt(P^2-D^2)``.

    The inverse of :func:`equivalent_vertical_freq_mhz`: given the reflection
    region's critical frequency, the maximum frequency this oblique path
    supports.
    """
    if group_range_km <= ground_distance_km:
        raise ValueError("group_range_km must exceed ground_distance_km")
    sec_phi = group_range_km / math.sqrt(group_range_km ** 2 - ground_distance_km ** 2)
    return critical_freq_mhz * sec_phi


def obliquity_factor(elevation_angle_deg: float,
                     h_iono_km: float = DEFAULT_IONO_HEIGHT_KM) -> float:
    """Slant→vertical obliquity factor M (thin-shell), capped at 10 (tec_geometry)."""
    theta = math.radians(elevation_angle_deg)
    sin_term = max(-1.0, min(1.0,
                             (R_EARTH_KM * math.cos(theta)) / (R_EARTH_KM + h_iono_km)))
    return min(1.0 / math.cos(math.asin(sin_term)), MAX_OBLIQUITY_FACTOR)


def slant_to_vertical_tec(tec_slant: float, elevation_angle_deg: float,
                          h_iono_km: float = DEFAULT_IONO_HEIGHT_KM
                          ) -> Tuple[float, float]:
    """Convert slant TEC to vertical TEC; returns (vtec, obliquity_factor)."""
    M = obliquity_factor(elevation_angle_deg, h_iono_km)
    return tec_slant / M, M


def group_delay_to_tec(group_delay_excess_s: float, frequency_hz: float) -> float:
    """Slant TEC (TECU) from excess group delay: ``TEC = c*f^2*dtau / K``."""
    tec_si = C_M_S * frequency_hz ** 2 * group_delay_excess_s / K_TEC
    return tec_si / TECU
