"""Ionospheric profile — IRI when available, parametric fallback otherwise.

Mirrors hf-timestd's tiered approach: prefer the empirical IRI model
(``iri2020``, the ``iono`` extra; needs a Fortran build) and fall back to a
coarse solar-zenith-driven parametric estimate (``tier="parametric"``) so a
foF2/hmF2 is always available.  IRI is the authoritative product; the parametric
tier is only a degraded stand-in.
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from hamsci_dsp.ionosphere.solar import solar_position

# Parametric tier knobs (coarse; IRI supersedes these).
_FOF2_NIGHT_MHZ = 3.0
_FOF2_DAY_MAX_MHZ = 11.0
_HMF2_DAY_KM = 300.0
_HMF2_NIGHT_KM = 350.0


@dataclass
class IonoState:
    fof2_mhz: float
    hmf2_km: float
    tec_tecu: Optional[float]
    tier: str            # "iri" | "parametric"


def _parametric(dt: datetime, lat: float, lon: float) -> IonoState:
    _, elev = solar_position(dt, lat, lon)
    chi = max(0.0, math.sin(math.radians(max(0.0, elev))))   # 0 at/below horizon
    # foF2 ~ (cos chi)^0.25 style dependence between a night floor and day max.
    fof2 = _FOF2_NIGHT_MHZ + (_FOF2_DAY_MAX_MHZ - _FOF2_NIGHT_MHZ) * (chi ** 0.25)
    hmf2 = _HMF2_DAY_KM if elev > 0 else _HMF2_NIGHT_KM
    return IonoState(fof2_mhz=fof2, hmf2_km=hmf2, tec_tecu=None, tier="parametric")


def ionosphere_state(dt: datetime, lat: float, lon: float) -> IonoState:
    """foF2 / hmF2 (+ TEC if IRI) for a time and location.

    Uses IRI when ``iri2020`` is importable, else the parametric fallback.
    """
    try:
        import iri2020  # type: ignore
    except Exception:
        return _parametric(dt, lat, lon)
    try:
        prof = iri2020.IRI(dt, [100, 1000, 50], lat, lon)
        fof2 = float(prof["foF2"].item())
        hmf2 = float(prof["hmF2"].item())
        tec = float(prof["TEC"].item()) / 1e16 if "TEC" in prof else None
        return IonoState(fof2_mhz=fof2, hmf2_km=hmf2, tec_tecu=tec, tier="iri")
    except Exception:
        return _parametric(dt, lat, lon)
