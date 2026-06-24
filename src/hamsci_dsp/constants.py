"""Physical constants shared across the sigmond propagation stack.

Consolidates the speed-of-light / ionospheric / Earth constants that were
redefined (in several unit forms) across hf-timestd, hf-tec, and codar-sounder.
"""
from __future__ import annotations

# Speed of light
C_M_S = 299_792_458.0            # m/s
C_KM_S = C_M_S / 1_000.0         # km/s
C_KM_MS = C_KM_S / 1_000.0       # km/ms

# Ionospheric group-delay / TEC constant: Δτ = (K_TEC / f²) · TEC  (SI).
# Phase advance and group delay share this 40.3 m³ s⁻² constant.
K_TEC = 40.3                     # m³ / s²

# 1 TEC unit = 1e16 electrons / m²
TECU = 1.0e16

# Mean Earth radius (same value the clients' haversines used).
R_EARTH_KM = 6371.0088
R_EARTH_M = R_EARTH_KM * 1_000.0
