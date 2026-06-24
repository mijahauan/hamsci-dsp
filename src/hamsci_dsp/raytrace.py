"""HF ray-tracing wrapper — HamSCI PyLAP / PHaRLAP.

Thin, lazy wrapper around the licence-restricted PHaRLAP engine (via the
``raytrace`` extra's ``pylap``).  Mirrors hf-timestd ``core/raytrace_engine.py``:
``is_available()`` is the gate, and the engine is an advisory physics overlay —
absent PyLAP/PHaRLAP it cleanly reports unavailable rather than raising, so the
analytic propagation layer (``hamsci_dsp.propagation``) always works without it.

PHaRLAP itself is DST-licence-restricted and never bundled; it must be staged
out-of-band (see hf-timestd ``scripts/install-pharlap.sh``).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List


@dataclass
class RayMode:
    n_hops: int
    group_delay_ms: float
    launch_elevation_deg: float
    ground_range_km: float


class RaytraceEngine:
    """Lazy PyLAP/PHaRLAP wrapper.  Construct cheaply; check is_available()."""

    def __init__(self) -> None:
        self._pylap = None
        self._checked = False

    def is_available(self) -> bool:
        """True only if PyLAP (and thus PHaRLAP) can be imported."""
        if not self._checked:
            self._checked = True
            try:
                import pylap  # type: ignore  # noqa: F401
                self._pylap = pylap
            except Exception:
                self._pylap = None
        return self._pylap is not None

    def compute_modes(self, *args, **kwargs) -> List[RayMode]:
        """Ray-trace propagation modes; ``[]`` when the engine is unavailable.

        The full 2-D/3-D NRT call signature follows hf-timestd
        ``core/raytrace_engine.py``; wiring the IRI-backed trace is done where
        PHaRLAP is installed (this wrapper keeps the import optional).
        """
        if not self.is_available():
            return []
        raise NotImplementedError(
            "PyLAP trace wiring is staged where PHaRLAP is installed; "
            "see hf-timestd core/raytrace_engine.py for the call sequence.")
