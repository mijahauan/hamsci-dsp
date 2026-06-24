"""dsp tests — SNR, noise floor, phase->Doppler, correlation, coherent stack."""
import numpy as np
import pytest

from hamsci_dsp import dsp


def test_peak_snr_db_envelope_known_value():
    rng = np.random.default_rng(0)
    # Rayleigh envelope of zero-mean complex Gaussian, per-component sigma=1
    # → median ~ sigma*sqrt(2 ln 2), so rayleigh_envelope_sigma recovers ~1.
    env = np.abs(rng.standard_normal(20000) + 1j * rng.standard_normal(20000))
    # peak 100x sigma → 40 dB
    snr = dsp.peak_snr_db_envelope(100.0, env)
    assert abs(snr - 40.0) < 0.5


def test_peak_snr_db_signed_known_value():
    rng = np.random.default_rng(1)
    noise = rng.standard_normal(20000)        # sigma = 1
    assert abs(dsp.peak_snr_db_signed(10.0, noise) - 20.0) < 0.3


def test_snr_nan_on_empty():
    assert np.isnan(dsp.peak_snr_db_envelope(1.0, []))
    assert np.isnan(dsp.peak_snr_db_signed(1.0, []))


def test_noise_floor_methods():
    x = np.array([1.0, 1.0, 1.0, 1.0, 100.0])   # one outlier
    assert dsp.noise_floor(x, method="median") == 1.0
    assert dsp.noise_floor(x, method="percentile", pct=30) == 1.0
    # mad-based floor stays near the bulk despite the outlier
    assert dsp.noise_floor(x, method="mad") < 2.0


def test_doppler_from_phase_recovers_tone():
    fs = 1000.0
    t = np.arange(2000) / fs
    f0 = 12.5                                   # Hz
    phase = 2 * np.pi * f0 * t
    dop = dsp.doppler_from_phase(phase, t)
    assert abs(np.median(dop) - f0) < 0.1
    assert abs(dsp.doppler_from_phase_slope(phase, t) - f0) < 1e-6


def test_fft_correlate_finds_lag_and_phase():
    n = 256
    rng = np.random.default_rng(3)
    replica = (rng.standard_normal(n) + 1j * rng.standard_normal(n)).astype(np.complex128)
    lag = 40
    rx = np.roll(replica, lag) * np.exp(1j * 0.7)   # shifted + phase rotated
    corr = dsp.fft_correlate(rx, replica)
    peak = int(np.argmax(np.abs(corr)))
    assert peak == lag
    assert abs(((np.angle(corr[peak]) - 0.7 + np.pi) % (2 * np.pi)) - np.pi) < 1e-6


def test_coherent_stack_range_doppler_peaks_at_injected_doppler():
    n_reps, n_bins = 64, 8
    rep_period = 0.1                            # s → 10 Hz ambiguity, 0.156 Hz res
    stack = dsp.CoherentStack(n_reps, n_bins)
    f_dop = 2.0                                 # Hz, within +/-5 Hz
    for k in range(n_reps):
        prof = np.zeros(n_bins, dtype=np.complex64)
        prof[3] = np.exp(2j * np.pi * f_dop * k * rep_period)   # tone in bin 3
        full = stack.push(prof)
    assert full
    rd = stack.range_doppler()
    axis = dsp.doppler_axis_hz(n_reps, rep_period)
    peak_dop = axis[np.argmax(np.abs(rd[:, 3]))]
    assert abs(peak_dop - f_dop) < 0.2


def test_coherent_stack_guards_shape_and_fill():
    s = dsp.CoherentStack(2, 4)
    with pytest.raises(ValueError):
        s.push(np.zeros(3, dtype=np.complex64))
    with pytest.raises(RuntimeError):
        s.range_doppler()
