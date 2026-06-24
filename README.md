# hamsci-dsp

Shared DSP / timing utilities for the [HamSCI](https://hamsci.org/) **sigmond**
SDR suite. This is the canonical home for code that several sigmond clients
otherwise carry as byte-identical copies.

It is an **importable library only** — no CLI, no systemd unit, no client
contract surface. Like `callhash` and `ka9q-python`, consumers pin it editable
from a sibling checkout so a `git pull` propagates with no reinstall:

```toml
# in a consumer's pyproject.toml
[tool.uv.sources]
hamsci-dsp = { path = "../hamsci-dsp", editable = true }
```

## Modules

| Module | What it provides |
|--------|------------------|
| `hamsci_dsp.timing` | `AuthorityReader` / `AuthoritySnapshot` — the consumer side of hf-timestd's `/run/hf-timestd/authority.json` (the RTP↔UTC offset + tier). Stdlib-only. |

The `timing` module is the canonical extraction of the reader that hf-tec,
codar-sounder, psk-recorder, and wspr-recorder each duplicated; the
`authority.json` schema-v1 contract itself is owned by
`hf-timestd/docs/METROLOGY.md §4.5.2`.

Planned (Phase 2, when the SuperDARN Doppler product lands): `carrier_tec`
(carrier phase → dTEC) and `coherent` (slow-time range-Doppler FFT), extracted
from hf-timestd and hf-tec respectively.

## Development

```bash
uv sync --extra dev
uv run pytest
```

## Authors

- Michael Hauan (AC0G) — https://github.com/mijahauan/hamsci-dsp
- Part of [HamSCI](https://hamsci.org/).
