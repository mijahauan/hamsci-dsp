"""propagation tests — carrier dTEC, oblique inversion + MUF, scintillation."""
import math

import numpy as np
import pytest

from hamsci_dsp.constants import C_M_S, K_TEC, TECU
from hamsci_dsp.propagation import (
    carrier,
    compute_scintillation,
    dtec_from_phase,
    equivalent_vertical_freq_mhz,
    obliquity_factor,
    oblique_muf_mhz,
    takeoff_zenith_deg,
    virtual_height_km,
)


# ----- oblique inversion -------------------------------------------------

def test_virtual_height_roundtrip():
    D, h, N = 1500.0, 300.0, 1
    P = math.sqrt(D ** 2 + (2 * N * h) ** 2)
    assert abs(virtual_height_km(P, D, N) - h) < 1e-6


def test_muf_is_inverse_of_equivalent_vertical_freq():
    fo, D = 10.0, 1500.0
    P = math.sqrt(D ** 2 + (2 * 300.0) ** 2)
    fv = equivalent_vertical_freq_mhz(fo, P, D)          # critical freq at apex
    muf = oblique_muf_mhz(fv, P, D)                       # back to path MUF
    assert abs(muf - fo) < 1e-6
    assert fv < fo                                        # vertical < oblique


def test_takeoff_zenith_and_obliquity_bounds():
    assert 0.0 < takeoff_zenith_deg(2000.0, 1500.0) < 90.0
    assert 1.0 <= obliquity_factor(20.0) <= 10.0
    assert obliquity_factor(90.0) == pytest.approx(1.0, abs=1e-6)  # overhead


def test_virtual_height_rejects_unphysical():
    with pytest.raises(ValueError):
        virtual_height_km(1000.0, 1500.0)                # P < D


# ----- carrier dTEC ------------------------------------------------------

def _phase_to_tecu(freq_mhz):
    return -(C_M_S * freq_mhz * 1e6) / (2.0 * np.pi * K_TEC * TECU)


def test_dtec_linear_in_phase():
    t = np.arange(60.0)
    # small per-step phase (<pi) so unwrap is identity — realistic carrier phase
    total_dphi = 6.0
    phase = np.linspace(0.0, total_dphi, t.size)
    r = dtec_from_phase(t, phase, frequency_mhz=10.0)
    assert r is not None
    expected_end = total_dphi * _phase_to_tecu(10.0)
    assert abs(r.dtec_tecu[-1] - expected_end) < 1e-9
    assert r.dtec_tecu[0] == pytest.approx(0.0)
    assert np.std(r.dtec_rate_tecu_per_s) < 1e-9     # constant slope
    assert r.n_cycle_slips == 0 and r.n_gaps == 0
    assert r.unwrap_quality == 1.0


def test_dtec_coasts_across_gap():
    # a >GAP_THRESHOLD_S dropout between sample 29 and 30; the phase change
    # spanning the gap is ambiguous and must be coasted out of dTEC.
    t = np.concatenate([np.arange(30.0), 200.0 + np.arange(30.0)])  # 170 s gap
    phase = np.linspace(0.0, 3.0, t.size)        # ~0.05 rad/step, clean unwrap
    phase[30:] += 2.0                             # extra jump across the gap
    r = dtec_from_phase(t, phase, frequency_mhz=10.0)
    assert r.n_gaps >= 1
    naive_end = 5.0 * _phase_to_tecu(10.0)        # if the +2.0 were kept
    coasted_end = 3.0 * _phase_to_tecu(10.0)      # ramp only
    assert abs(r.dtec_tecu[-1] - coasted_end) < abs(naive_end - coasted_end) / 4


def test_dtec_none_when_too_short():
    assert dtec_from_phase([0.0, 1.0], [0.0, 1.0], 10.0) is None


# ----- scintillation -----------------------------------------------------

def test_scintillation_quiet_carrier_is_weak():
    # steady carrier + small noise → low S4, low sigma_phi
    rng = np.random.default_rng(0)
    z = (1.0 + 0.01 * rng.standard_normal(60)) * np.exp(
        1j * 0.01 * rng.standard_normal(60))
    res = compute_scintillation(z, sample_rate_hz=1.0)
    assert res.s4_index < 0.5
    assert res.s4_severity == "weak"


def test_scintillation_strong_fading_raises_s4():
    rng = np.random.default_rng(1)
    # heavy Rayleigh-like fading → large S4
    z = (rng.standard_normal(60) + 1j * rng.standard_normal(60))
    res = compute_scintillation(z, sample_rate_hz=1.0)
    assert res.s4_index > 0.5


def test_scintillation_handles_degenerate_input():
    res = compute_scintillation(np.zeros(60, dtype=complex), sample_rate_hz=1.0)
    assert res.s4_severity in ("unknown", "weak")   # never raises
