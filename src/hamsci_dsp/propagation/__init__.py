"""Propagation-physics layer: path observables from a known transmitter.

- carrier:      phase -> dTEC / dTEC-dt (TID/flare signature)
- oblique:      group path -> virtual height, equivalent vertical freq, MUF
- scintillation: S4 (amplitude) + sigma_phi (phase), ITU-R P.531 (HF-recalibrated)
"""
from hamsci_dsp.propagation.carrier import CarrierDTEC, dtec_from_phase
from hamsci_dsp.propagation.oblique import (
    classify_layer,
    equivalent_vertical_freq_mhz,
    equivalent_vertical_freq_uncertainty_mhz,
    group_delay_to_tec,
    obliquity_factor,
    oblique_muf_mhz,
    slant_to_vertical_tec,
    takeoff_zenith_deg,
    virtual_height_km,
    virtual_height_uncertainty_km,
)
from hamsci_dsp.propagation.scintillation import (
    ScintillationResult,
    compute_scintillation,
)

__all__ = [
    "CarrierDTEC", "dtec_from_phase",
    "virtual_height_km", "equivalent_vertical_freq_mhz", "takeoff_zenith_deg",
    "classify_layer", "virtual_height_uncertainty_km",
    "equivalent_vertical_freq_uncertainty_mhz", "oblique_muf_mhz",
    "obliquity_factor", "slant_to_vertical_tec", "group_delay_to_tec",
    "ScintillationResult", "compute_scintillation",
]
