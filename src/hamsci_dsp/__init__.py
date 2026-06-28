"""hamsci-dsp — shared DSP / timing utilities for the HamSCI sigmond suite.

This is the canonical home for code that several sigmond clients otherwise
duplicate.  It is an importable library only — no CLI, no systemd, no client
contract surface — pinned by each consumer via
``[tool.uv.sources] hamsci-dsp = { path = "../hamsci-dsp", editable = true }``.

Modules:
  timing  — AuthorityReader / AuthoritySnapshot: the consumer side of
            hf-timestd's /run/hf-timestd/authority.json (RTP↔UTC offset);
            acquire_anchor_utc: the one shared RTP->UTC anchor every
            recorder pins at stream start (RTP timestamp + authority offset).
            Epoch-aligned slot *boundaries* live in ka9q.SlotClock, not here.
"""

__version__ = "0.3.0"
