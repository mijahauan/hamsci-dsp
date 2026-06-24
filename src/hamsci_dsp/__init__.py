"""hamsci-dsp — shared DSP / timing utilities for the HamSCI sigmond suite.

This is the canonical home for code that several sigmond clients otherwise
duplicate.  It is an importable library only — no CLI, no systemd, no client
contract surface — pinned by each consumer via
``[tool.uv.sources] hamsci-dsp = { path = "../hamsci-dsp", editable = true }``.

Modules:
  timing  — AuthorityReader / AuthoritySnapshot: the consumer side of
            hf-timestd's /run/hf-timestd/authority.json (RTP↔UTC offset).
"""

__version__ = "0.2.0"
