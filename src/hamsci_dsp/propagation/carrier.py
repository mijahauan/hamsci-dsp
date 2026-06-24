"""Carrier phase → differential TEC (dTEC) and dTEC/dt.

The flagship propagation product: a received carrier's phase is proportional to
the ionospheric TEC along the path, so the unwrapped phase gives a relative TEC
time series and its derivative the TEC rate — the TID / flare signature behind
HamSCI GRAPE and hf-timestd.

Physics + cycle-slip/gap handling are math-identical to hf-timestd
``core/carrier_tec.py`` (P-M3): dTEC is taken DIRECTLY from phase
(``ΔsTEC = -(c·f)/(2π·K)·(φ-φ₀)``), not by re-integrating Doppler, and the
inter-sample step across a cycle slip or long gap is removed so the series
coasts rather than jumps.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from hamsci_dsp.constants import C_M_S, K_TEC, TECU

# A dropout longer than this makes the unwrapped phase across it ambiguous.
GAP_THRESHOLD_S = 120.0
# Phase acceleration beyond this (Hz/s) is a cycle slip, not ionospheric.
CYCLE_SLIP_HZ_PER_S = 5.0


@dataclass
class CarrierDTEC:
    epochs: np.ndarray            # seconds (unix or relative)
    dtec_tecu: np.ndarray         # relative TEC (TECU), starts at 0
    dtec_rate_tecu_per_s: np.ndarray
    frequency_mhz: float
    n_cycle_slips: int
    n_gaps: int
    unwrap_quality: float         # 0..1 risk score (1 = clean)
    n_points: int


def dtec_from_phase(epochs, carrier_phase_rad, frequency_mhz: float):
    """Relative TEC + TEC rate from a carrier-phase time series.

    Returns a :class:`CarrierDTEC`, or ``None`` if fewer than 3 usable points.
    ``epochs`` and ``carrier_phase_rad`` are 1-D arrays of equal length.
    """
    epochs = np.asarray(epochs, dtype=np.float64)
    phase = np.asarray(carrier_phase_rad, dtype=np.float64)
    if epochs.size < 3 or epochs.size != phase.size:
        return None

    phase_unwrapped = np.unwrap(phase)

    # Unwrap RISK indicator (P-H3): post-unwrap steps near the π Nyquist edge.
    dphi_raw = np.diff(phase)
    dphi_raw_wrapped = (dphi_raw + np.pi) % (2 * np.pi) - np.pi
    n_jumps = int(np.sum(np.abs(dphi_raw_wrapped) > (np.pi / 2)))
    unwrap_quality = max(0.0, 1.0 - n_jumps / max(dphi_raw_wrapped.size, 1))

    dt = np.diff(epochs)
    dphi = np.diff(phase_unwrapped)
    # Doppler — used ONLY to detect cycle slips (not to derive dTEC).
    with np.errstate(divide="ignore", invalid="ignore"):
        doppler_hz = -(1.0 / (2.0 * np.pi)) * dphi / dt
    d2phi = np.zeros_like(doppler_hz)
    d2phi[1:] = np.diff(doppler_hz)
    slip_mask = np.abs(d2phi) > CYCLE_SLIP_HZ_PER_S
    n_cycle_slips = int(np.sum(slip_mask))

    gap_mask = dt > GAP_THRESHOLD_S
    n_gaps = int(np.sum(gap_mask))

    # P-M3: relative TEC directly from phase; coast across slips/gaps.
    bad_step = slip_mask | gap_mask
    phase_corrected = phase_unwrapped.copy()
    phase_corrected[1:] -= np.cumsum(np.where(bad_step, dphi, 0.0))

    freq_hz = frequency_mhz * 1e6
    phase_to_tecu = -(C_M_S * freq_hz) / (2.0 * np.pi * K_TEC * TECU)
    dtec_tecu = (phase_corrected - phase_corrected[0]) * phase_to_tecu
    dtec_rate = np.gradient(dtec_tecu, epochs)

    return CarrierDTEC(
        epochs=epochs,
        dtec_tecu=dtec_tecu,
        dtec_rate_tecu_per_s=dtec_rate,
        frequency_mhz=frequency_mhz,
        n_cycle_slips=n_cycle_slips,
        n_gaps=n_gaps,
        unwrap_quality=unwrap_quality,
        n_points=int(epochs.size),
    )
