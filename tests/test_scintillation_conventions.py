"""Physics-anchored scintillation tests: synthetic S4/sigma_phi injection.

These verify the *kernel math* against known ground truth (recover an injected
intensity coefficient-of-variation; recover an injected phase-fluctuation std)
and the *methodology* (the coupled detrend/window/threshold convention),
instead of freezing whatever the implementation happens to emit. They are the
reason the convention choice is reversible and both conventions stay honest.
"""
import math

import numpy as np
import pytest

from hamsci_dsp.propagation import (
    HF_OBLIQUE,
    ITU_R_LBAND,
    compute_scintillation,
    reclassify,
)


# ── A. S4 == coefficient of variation of intensity, recovered from injection ──
# S4 = std(I)/mean(I). A symmetric two-level intensity {1-s4, 1+s4} has exactly
# that CoV, positive support for s4<1, and no sample beyond the MAD-rejection
# bound — so recovery is exact and deterministic (no RNG, no outlier trimming).
@pytest.mark.parametrize("s4_true", [0.2, 0.4, 0.7])
def test_s4_recovers_injected_coefficient_of_variation(s4_true):
    n = 60
    intensity = np.array([1.0 - s4_true, 1.0 + s4_true] * (n // 2))
    z = np.sqrt(intensity).astype(np.complex128)        # phase 0 -> sigma_phi axis untouched
    r = compute_scintillation(z, sample_rate_hz=1.0, convention=HF_OBLIQUE)
    assert r.s4_index == pytest.approx(s4_true, rel=1e-6)
    assert r.n_outliers_rejected == 0


def test_s4_above_unity_is_not_clipped_focusing():
    # Refractive-focusing regime: a broad (not single-outlier) spread gives a
    # genuine S4>1 that the kernel must preserve. Two-point {0, h} with fraction
    # p=1/(1+s4^2) at h=1/p yields S4=sqrt((1-p)/p); the spread is intrinsic, so
    # MAD rejection (bad-sweep protection) leaves it intact.
    s4_true = 1.5
    n = 400
    p = 1.0 / (1.0 + s4_true**2)
    k = int(round(p * n))
    intensity = np.concatenate([np.full(k, 1.0 / p), np.zeros(n - k)])
    z = np.sqrt(intensity).astype(np.complex128)
    r = compute_scintillation(z, sample_rate_hz=1.0, convention=HF_OBLIQUE)
    assert r.s4_index > 1.0
    assert r.s4_index == pytest.approx(s4_true, rel=0.05)


# ── B. sigma_phi: quadratic removes TEC curvature, linear leaves it (detrend) ──
def test_quadratic_detrend_recovers_fluctuation_linear_inflates():
    n = 60
    t = np.arange(n, dtype=float)
    rng = np.random.default_rng(2)
    sigma_inject = 0.30                                  # rad, true scintillation band
    fluct = rng.normal(0.0, sigma_inject, n)
    tec_curve = 0.05 * t + 0.002 * t**2                  # Doppler + quadratic TEC curvature
    z = np.exp(1j * (tec_curve + fluct))                 # unit amplitude -> no intensity outliers
    r = compute_scintillation(z, sample_rate_hz=1.0, convention=HF_OBLIQUE)
    # quadratic detrend removes the curvature -> recovers the injected fluctuation
    assert r.sigma_phi_quadratic_rad == pytest.approx(sigma_inject, rel=0.25)
    # linear detrend cannot track the t^2 term -> residual curvature inflates it
    assert r.sigma_phi_linear_rad > 1.5 * r.sigma_phi_quadratic_rad
    assert r.sigma_phi_underfit_ratio > 1.5
    # HF convention bins on the quadratic value
    assert r.convention.detrend_order == 2
    assert r.sigma_phi_rad == pytest.approx(r.sigma_phi_quadratic_rad)


# ── C. sigma_phi depends on WINDOW for the SAME process (why window is pinned) ──
# Single low-frequency tone, no extra trend. A polynomial detrend is a high-pass
# with cutoff ~ order/window: a SHORT window (tone ~ a slow arc) absorbs the tone
# into the parabola and DEFLATES sigma_phi; a LONG window (many cycles) cannot
# fit it and PRESERVES it. Same physics, different sigma_phi -> window must be
# part of the convention. (Direction is the reverse of the "long absorbs" guess.)
def test_sigma_phi_is_window_dependent_for_a_fixed_process():
    A, period_s = 0.8, 100.0

    def segment(n):
        t = np.arange(n, dtype=float)
        return np.exp(1j * (A * np.sin(2 * np.pi * t / period_s)))

    short = compute_scintillation(segment(20), sample_rate_hz=1.0, convention=HF_OBLIQUE)
    long_ = compute_scintillation(segment(600), sample_rate_hz=1.0, convention=HF_OBLIQUE)
    assert short.sigma_phi_rad < 0.5 * long_.sigma_phi_rad      # short window deflates the tone
    assert long_.sigma_phi_rad == pytest.approx(A / math.sqrt(2), rel=0.15)
    assert not short.window_ok                                 # ~20s flagged off the 60s convention
    assert short.window_s < 30.0 < 300.0 < long_.window_s      # cutoff (~order/window) moved


# ── D. severity is convention-relative and reversible (reclassify == recompute) ──
def test_reclassify_matches_recompute_and_leaves_raw_indices_untouched():
    rng = np.random.default_rng(3)
    n = 60
    intensity = rng.gamma(shape=2.0, scale=0.5, size=n)        # CoV = 1/sqrt(2) ~ 0.707
    z = np.sqrt(intensity).astype(np.complex128) * np.exp(1j * rng.normal(0, 0.4, n))

    hf = compute_scintillation(z, sample_rate_hz=1.0, convention=HF_OBLIQUE)
    itu_direct = compute_scintillation(z, sample_rate_hz=1.0, convention=ITU_R_LBAND)
    itu_reclass = reclassify(hf, ITU_R_LBAND)

    # raw indices are convention-free
    assert itu_reclass.s4_index == hf.s4_index
    # S4 ~0.707 is "weak" under HF (edge 1.0) but "strong" under ITU-R (edge 0.6)
    assert hf.s4_severity == "weak" and itu_reclass.s4_severity == "strong"
    # reclassify is EXACT vs a fresh recompute on the detrend+threshold axes
    # (both detrend orders are retained on the result), so no raw samples needed
    assert itu_reclass.s4_severity == itu_direct.s4_severity
    assert itu_reclass.sigma_phi_severity == itu_direct.sigma_phi_severity
    assert itu_reclass.sigma_phi_rad == pytest.approx(itu_direct.sigma_phi_rad)
    # convention picks which detrend feeds severity (HF=quadratic, ITU=linear)
    assert hf.sigma_phi_rad == hf.sigma_phi_quadratic_rad
    assert itu_reclass.sigma_phi_rad == hf.sigma_phi_linear_rad
    # never a naked label: provenance + observable note travel with the result
    assert hf.convention.observable_note and hf.convention.calibration
    assert itu_reclass.convention.name == "ITU-R-Lband-P531"
