"""Tests for hamsci_dsp.timing.AuthorityReader.

Mirrors the behaviour the sibling clients (hf-tec / codar-sounder /
psk-recorder / wspr-recorder) rely on: all error paths return None rather
than raising, schema/freshness are enforced, and the provenance block shape
is stable.
"""
import json
from datetime import datetime, timedelta, timezone

from hamsci_dsp.timing import (
    AuthorityReader,
    AuthoritySnapshot,
    acquire_anchor_utc,
    standalone_timing_authority,
)

_NOW = datetime(2026, 6, 23, 12, 0, 0, tzinfo=timezone.utc)


def _write(tmp_path, payload):
    p = tmp_path / "authority.json"
    p.write_text(json.dumps(payload), encoding="utf-8")
    return p


def _fresh_payload(**overrides):
    base = {
        "schema": "v1",
        "utc_published": _NOW.isoformat(),
        "a_level": "A1",
        "t_level_active": "T3",
        "t_level_available": ["T3", "T4"],
        "t_level_witnesses": ["WWV"],
        "rtp_to_utc_offset_ns": 1_500_000,
        "sigma_ns": 2000,
        "stations_contributing": ["WWV"],
        "last_transition_utc": _NOW.isoformat(),
        "disagreement_flags": [],
        "governor_radiod": "fhe-rx888",
    }
    base.update(overrides)
    return base


def test_reads_fresh_snapshot(tmp_path):
    p = _write(tmp_path, _fresh_payload())
    snap = AuthorityReader(path=p, now_fn=lambda: _NOW).read()
    assert snap is not None
    assert snap.offset_usable
    assert snap.rtp_to_utc_offset_ns == 1_500_000
    assert abs(snap.offset_seconds - 0.0015) < 1e-12
    block = snap.to_timing_authority(client_radiod="fhe-rx888")
    assert block["source"] == "hf-timestd-authority"
    assert block["client_radiod"] == "fhe-rx888"
    assert block["rtp_to_utc_offset_ns"] == 1_500_000


def test_missing_file_returns_none(tmp_path):
    snap = AuthorityReader(path=tmp_path / "nope.json", now_fn=lambda: _NOW).read()
    assert snap is None


def test_stale_snapshot_returns_none(tmp_path):
    p = _write(tmp_path, _fresh_payload())
    later = _NOW + timedelta(seconds=120)
    snap = AuthorityReader(path=p, freshness_sec=60.0, now_fn=lambda: later).read()
    assert snap is None


def test_unsupported_schema_returns_none(tmp_path):
    p = _write(tmp_path, _fresh_payload(schema="v999"))
    assert AuthorityReader(path=p, now_fn=lambda: _NOW).read() is None


def test_malformed_json_returns_none(tmp_path):
    p = tmp_path / "authority.json"
    p.write_text("{ not json", encoding="utf-8")
    assert AuthorityReader(path=p, now_fn=lambda: _NOW).read() is None


def test_offset_not_usable_when_absent(tmp_path):
    p = _write(tmp_path, _fresh_payload(t_level_active=None, rtp_to_utc_offset_ns=None))
    snap = AuthorityReader(path=p, now_fn=lambda: _NOW).read()
    assert snap is not None
    assert not snap.offset_usable


def test_negative_offset_handled(tmp_path):
    # A behind-real-time radiod yields a negative RTP->UTC offset; it must
    # round-trip with sign intact (clients add it to the anchor UTC).
    p = _write(tmp_path, _fresh_payload(rtp_to_utc_offset_ns=-1_234_567))
    snap = AuthorityReader(path=p, now_fn=lambda: _NOW).read()
    assert snap is not None
    assert snap.rtp_to_utc_offset_ns == -1_234_567
    assert abs(snap.offset_seconds - (-0.001234567)) < 1e-12


def test_governor_radiod_none_when_absent(tmp_path):
    payload = _fresh_payload()
    del payload["governor_radiod"]
    snap = AuthorityReader(path=_write(tmp_path, payload), now_fn=lambda: _NOW).read()
    assert snap is not None
    assert snap.governor_radiod is None


# ── acquire_anchor_utc ────────────────────────────────────────────────────

class _Snap:
    """Minimal AuthoritySnapshot stand-in (offset usable)."""
    def __init__(self, offset_ns=2_000_000):
        self.rtp_to_utc_offset_ns = offset_ns
        self.t_level_active = "T3"

    @property
    def offset_usable(self):
        return self.t_level_active is not None and self.rtp_to_utc_offset_ns is not None

    @property
    def offset_seconds(self):
        return (self.rtp_to_utc_offset_ns or 0) / 1e9


def _rtp_to_utc_ok(rtp, ci, wallclock_hint_sec=None):
    # Pretend radiod's RTP maps to a fixed GPS-true instant.
    return 1_700_000_000.0


def _rtp_to_utc_none(rtp, ci, wallclock_hint_sec=None):
    return None


def test_anchor_rtp_referenced_with_authority():
    a = acquire_anchor_utc(
        first_rtp=12345, channel_info=object(), rtp_to_utc=_rtp_to_utc_ok,
        snapshot=_Snap(offset_ns=2_000_000),  # +2 ms
    )
    assert a.rtp_referenced
    assert a.source == "rtp_to_utc+authority"
    assert abs(a.utc - (1_700_000_000.0 + 0.002)) < 1e-9
    assert a.offset_ns == 2_000_000


def test_anchor_rtp_referenced_no_authority():
    a = acquire_anchor_utc(
        first_rtp=12345, channel_info=object(), rtp_to_utc=_rtp_to_utc_ok,
        snapshot=None,
    )
    assert a.rtp_referenced
    assert a.source == "rtp_to_utc"
    assert a.utc == 1_700_000_000.0
    assert a.offset_seconds == 0.0


def test_anchor_falls_back_when_no_channel_info():
    # samples_behind names the first held sample, not "now".
    a = acquire_anchor_utc(
        first_rtp=None, channel_info=None, rtp_to_utc=_rtp_to_utc_ok,
        snapshot=None, samples_behind=2400, sample_rate=12000,
        now_fn=lambda: 1_700_000_500.0,
    )
    assert not a.rtp_referenced
    assert a.source == "wallclock_fallback"
    assert abs(a.utc - (1_700_000_500.0 - 0.2)) < 1e-9


def test_anchor_fallback_applies_authority_offset():
    a = acquire_anchor_utc(
        first_rtp=None, channel_info=None, rtp_to_utc=_rtp_to_utc_ok,
        snapshot=_Snap(offset_ns=5_000_000), now_fn=lambda: 1_700_000_500.0,
    )
    assert not a.rtp_referenced
    assert a.source == "authority_on_wallclock"
    assert abs(a.utc - (1_700_000_500.0 + 0.005)) < 1e-9


def test_anchor_falls_back_when_rtp_to_utc_returns_none():
    a = acquire_anchor_utc(
        first_rtp=12345, channel_info=object(), rtp_to_utc=_rtp_to_utc_none,
        snapshot=None, now_fn=lambda: 1_700_000_500.0,
    )
    assert not a.rtp_referenced
    assert a.source == "wallclock_fallback"
    assert a.utc == 1_700_000_500.0


def test_anchor_reads_injected_authority_reader():
    class _Reader:
        def read(self):
            return _Snap(offset_ns=1_000_000)
    a = acquire_anchor_utc(
        first_rtp=1, channel_info=object(), rtp_to_utc=_rtp_to_utc_ok,
        authority_reader=_Reader(),
    )
    assert a.source == "rtp_to_utc+authority"
    assert a.snapshot is not None


def test_anchor_survives_authority_reader_exception():
    class _BadReader:
        def read(self):
            raise RuntimeError("boom")
    a = acquire_anchor_utc(
        first_rtp=1, channel_info=object(), rtp_to_utc=_rtp_to_utc_ok,
        authority_reader=_BadReader(),
    )
    # Degrades to no-authority RTP path, never raises.
    assert a.rtp_referenced and a.source == "rtp_to_utc"


def test_anchor_datetime_property():
    a = acquire_anchor_utc(
        first_rtp=1, channel_info=object(), rtp_to_utc=_rtp_to_utc_ok, snapshot=None,
    )
    assert a.datetime.tzinfo is timezone.utc
    assert abs(a.datetime.timestamp() - 1_700_000_000.0) < 1e-6


def test_standalone_block_shape_matches():
    block = standalone_timing_authority(client_radiod="fhe-rx888")
    assert block["source"] == "standalone-fallback"
    assert block["rtp_to_utc_offset_ns"] is None
    assert block["client_radiod"] == "fhe-rx888"
    # Same keys as the live block so consumers can treat them uniformly.
    live_keys = {
        "source", "schema", "a_level", "t_level_active", "t_level_witnesses",
        "rtp_to_utc_offset_ns", "sigma_ns", "disagreement_flags",
        "governor_radiod", "client_radiod", "authority_utc_published",
    }
    assert set(block) == live_keys
