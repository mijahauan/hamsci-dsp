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
