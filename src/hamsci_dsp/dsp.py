"""Low-level DSP primitives shared by the sigmond clients.

Consolidates pieces that several clients implemented separately:

* canonical peak SNR (Rayleigh-envelope / signed-Gaussian) — moved verbatim
  from hf-timestd ``core/snr.py`` (its review made it the single source of truth).
* robust noise-floor estimation (median / percentile / MAD) — unifying the
  median floor (codar/superdarn pulse detectors) and the 30th-percentile floor
  (hf-tec ``detect.py``).
* ``CoherentStack`` slow-time range-Doppler integration — from hf-tec
  ``core/coherent.py``.
* carrier phase → instantaneous Doppler, and FFT cross-correlation.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional, Sequence, Union

import numpy as np

_FloatArray = Union[np.ndarray, Sequence[float]]

# median(Rayleigh) = sigma * sqrt(2 ln 2); divide to recover sigma.
_RAYLEIGH_MEDIAN_FACTOR = math.sqrt(2.0 * math.log(2.0))  # ~1.1774


# --------------------------------------------------------------------------
# SNR (canonical — verbatim from hf-timestd/core/snr.py)
# --------------------------------------------------------------------------

def rayleigh_envelope_sigma(envelope_samples: _FloatArray) -> float:
    """Underlying noise sigma from a Rayleigh-distributed envelope:
    ``sigma = median(env) / sqrt(2 ln 2)`` (robust to outliers). 0.0 if empty."""
    arr = np.asarray(envelope_samples, dtype=np.float64).ravel()
    if arr.size == 0:
        return 0.0
    return float(np.median(arr)) / _RAYLEIGH_MEDIAN_FACTOR


def peak_snr_db_envelope(peak: float, noise_envelope: _FloatArray, *,
                         sigma_floor: float = 1e-10) -> float:
    """Canonical peak SNR (dB) for Rayleigh-envelope noise (complex-IQ matched
    filter): ``20*log10(|peak| / sigma_hat)``.  NaN if sigma is unmeasurable."""
    sigma = rayleigh_envelope_sigma(noise_envelope)
    if sigma <= 0:
        return float("nan")
    return 20.0 * math.log10(abs(float(peak)) / max(sigma, sigma_floor))


def peak_snr_db_signed(peak: float, noise_samples: _FloatArray, *,
                       sigma_floor: float = 1e-10) -> float:
    """Canonical peak SNR (dB) for zero-mean signed-Gaussian noise (real
    correlation): ``20*log10(|peak| / std(noise))``.  NaN if unmeasurable."""
    arr = np.asarray(noise_samples, dtype=np.float64).ravel()
    if arr.size == 0:
        return float("nan")
    sigma = float(np.std(arr))
    if sigma <= 0:
        return float("nan")
    return 20.0 * math.log10(abs(float(peak)) / max(sigma, sigma_floor))


# --------------------------------------------------------------------------
# Noise floor
# --------------------------------------------------------------------------

def mad(x: _FloatArray) -> float:
    """Median absolute deviation."""
    arr = np.asarray(x, dtype=np.float64).ravel()
    if arr.size == 0:
        return 0.0
    return float(np.median(np.abs(arr - np.median(arr))))


def noise_floor(x: _FloatArray, *, method: str = "median",
                pct: float = 30.0) -> float:
    """Robust noise-floor of a power array.

    method="median"     — np.median (codar / superdarn pulse detectors)
    method="percentile" — np.percentile at ``pct`` (hf-tec detect.py)
    method="mad"        — median + 1.4826*MAD (sigma-scaled robust floor)
    """
    arr = np.asarray(x, dtype=np.float64).ravel()
    if arr.size == 0:
        return 0.0
    if method == "median":
        return float(np.median(arr))
    if method == "percentile":
        return float(np.percentile(arr, pct))
    if method == "mad":
        return float(np.median(arr) + 1.4826 * mad(arr))
    raise ValueError(f"unknown method {method!r}")


# --------------------------------------------------------------------------
# Carrier phase -> Doppler
# --------------------------------------------------------------------------

def unwrap_phase(phase_rad: _FloatArray) -> np.ndarray:
    """np.unwrap with float64 output."""
    return np.unwrap(np.asarray(phase_rad, dtype=np.float64))


def doppler_from_phase(phase_rad: _FloatArray, t_s: _FloatArray) -> np.ndarray:
    """Instantaneous Doppler (Hz) = (1/2pi) d(phi)/dt, from carrier phase.

    Phase is unwrapped first; uses ``np.gradient`` so the output matches the
    input length.  (Sign: increasing phase → positive Doppler.)
    """
    phi = unwrap_phase(phase_rad)
    t = np.asarray(t_s, dtype=np.float64)
    return np.gradient(phi, t) / (2.0 * np.pi)


def doppler_from_phase_slope(phase_rad: _FloatArray, t_s: _FloatArray) -> float:
    """Single Doppler estimate (Hz) from a linear fit to unwrapped phase —
    robust for a short coherent window."""
    phi = unwrap_phase(phase_rad)
    t = np.asarray(t_s, dtype=np.float64)
    slope = float(np.polyfit(t, phi, 1)[0])
    return slope / (2.0 * np.pi)


# --------------------------------------------------------------------------
# FFT cross-correlation
# --------------------------------------------------------------------------

def fft_correlate(rx: _FloatArray, replica: _FloatArray) -> np.ndarray:
    """Circular cross-correlation of ``rx`` against ``replica`` via FFT.

    Returns the complex correlation (length max(len(rx), len(replica))).  Peak
    magnitude index is the lag; phase at the peak is the carrier phase.
    """
    a = np.asarray(rx, dtype=np.complex128)
    b = np.asarray(replica, dtype=np.complex128)
    n = max(a.size, b.size)
    A = np.fft.fft(a, n)
    B = np.fft.fft(b, n)
    return np.fft.ifft(A * np.conj(B))


# --------------------------------------------------------------------------
# Coherent slow-time range-Doppler stack (from hf-tec/core/coherent.py)
# --------------------------------------------------------------------------

@dataclass
class CoherentStack:
    """Stack N successive complex range profiles, FFT along slow-time."""
    n_reps: int
    n_range_bins: int
    _buffer: np.ndarray = field(init=False, repr=False)
    _fill: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        self._buffer = np.zeros((self.n_reps, self.n_range_bins), dtype=np.complex64)
        self._fill = 0

    def push(self, range_profile: np.ndarray) -> bool:
        if range_profile.shape != (self.n_range_bins,):
            raise ValueError(
                f"range_profile shape {range_profile.shape} != ({self.n_range_bins},)")
        self._buffer[self._fill, :] = range_profile.astype(np.complex64, copy=False)
        self._fill += 1
        return self._fill >= self.n_reps

    def is_full(self) -> bool:
        return self._fill >= self.n_reps

    def reset(self) -> None:
        self._buffer.fill(0)
        self._fill = 0

    def range_doppler(self) -> np.ndarray:
        """Range-Doppler matrix (FFT along slow-time / axis 0)."""
        if not self.is_full():
            raise RuntimeError(f"stack not full ({self._fill}/{self.n_reps})")
        return np.fft.fft(self._buffer, axis=0).astype(np.complex64)


def doppler_axis_hz(n_reps: int, rep_period_s: float) -> np.ndarray:
    """Doppler axis (Hz, FFT order) for a CoherentStack range-Doppler matrix."""
    return np.fft.fftfreq(n_reps, d=rep_period_s).astype(np.float64)
