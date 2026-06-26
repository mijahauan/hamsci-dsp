# hamsci-dsp — Requirements Specification

**Status:** v0.1 baseline (retroactive). **Owner:** Michael Hauan (AC0G).
**Last reconciled against code:** hamsci-dsp `0.2.0` (2026-06-25).
**Prefix:** `DSP`.

> Retroactive application of [sigmond/docs/REQUIREMENTS-TEMPLATE.md](https://github.com/HamSCI/sigmond/blob/main/docs/REQUIREMENTS-TEMPLATE.md)
> to a **shared library**, not a contract client. hamsci-dsp has no CLI, no
> systemd unit, and no client-contract surface; its "interface" is its **public
> Python API** (§8.3), most load-bearing of which is the timing
> `AuthorityReader` — the **consumer side** of the contract §18 timing authority
> that every RF client uses. The sigmond↔client contract therefore **does not
> apply here**; consuming clients reference it in their own docs. This library's
> reason for being is **de-duplication**: it is the single home for DSP / timing
> / geometry / propagation code that several clients otherwise carry as
> byte-identical copies, and that migration (#18 hamsci-dsp dedup epic) is
> **ongoing** — so expect a mix of `✅` (extracted, tested, consumed) and `🟡`
> (extracted here but clients still carry duplicates) honestly recorded.
> Tags: `[DOC]` documented · `[CODE]` implicit-in-code · `[NEW]` surfaced by this
> review. Status: `✅` implemented/verified · `🟡` partial/unverified · `⬜` planned.

## 1. Context & problem statement

Across the sigmond suite the same physics and timing math was written over and
over: great-circle distance/bearing was reimplemented 19+ times (hf-timestd alone
carried ~17 copies, plus a separate inline Vincenty in wspr-recorder); peak-SNR,
robust noise-floor, carrier-phase→dTEC, oblique virtual-height inversion, and
scintillation indices each existed in two or three subtly-different forms; and the
**consumer side of hf-timestd's `authority.json`** (the contract §18 timing
authority) was copied byte-identically into hf-tec, codar-sounder, psk-recorder,
and wspr-recorder. Duplication of *physics* is a correctness hazard — two copies
of an inversion drift apart and silently disagree on a science product — and
duplication of the *authority reader* means a schema or freshness-policy fix has to
be made in five places.

hamsci-dsp is the **single source of truth** for that shared code. Like
`ka9q-python` and `callhash`, it is an importable library pinned editable from a
sibling checkout, so a `git pull` propagates to every consumer's venv with no
reinstall. Its defining design principle is *extract math-identical, test once,
consume everywhere*: each module is lifted verbatim from the client whose review
made it canonical (timing/SNR/carrier-dTEC from hf-timestd; oblique-inversion and
scintillation from codar; coherent-stack from hf-tec), given one tested
implementation here, and the clients are then rewired onto it.

That rewiring is deliberately **opportunistic and incomplete** as of v0.2: a
module is migrated when it is next touched, so the library can already be the
authority for new code (superdarn-sounder consumes timing/geometry/propagation
from day one; hf-timestd has moved its geometry here) while older clients still
run their local copies (the four AuthorityReader duplicates, hf-timestd's
`snr.py`/`carrier_tec.py`/`tec_geometry.py`). This document captures the library's
requirements *and* the honest state of that migration.

## 2. Goals & objectives

- Be the **one tested implementation** of each shared primitive — geodesy,
  hop/reflection geometry, SNR/noise-floor, carrier-dTEC, oblique inversion,
  scintillation, coherent range-Doppler — so no two clients disagree on a physics
  result.
- Own the **canonical consumer of the §18 timing authority** (`AuthorityReader`,
  `AuthoritySnapshot`, `to_timing_authority`, `standalone_timing_authority`) so
  every RF client labels frames against `authority.json` identically.
- Stay **light and universally installable**: a stdlib-only `timing`/`constants`
  core, a numpy+geographiclib numeric core, and heavy scientific engines
  (IRI, PyLAP/PHaRLAP, apexpy) gated behind extras.
- Provide a **stable public API** keyed off explicit module/function names so
  consumers can pin `>=0.2` and trust it.
- **Drive duplication out of the suite**: every extracted module SHALL have its
  client duplicates retired (the #18 dedup migration), measurable as "zero local
  copies remain."

## 3. Non-goals / out of scope

- **Producing the timing authority.** It only *reads* `authority.json`; the
  producer is hf-timestd (its `HFT-I-002`). The schema is owned by
  `hf-timestd/docs/METROLOGY.md §4.5.2`, not here.
- **Being a client.** No CLI, no `inventory`/`validate`, no systemd unit, no
  deploy.toml, no shared-sink writes — those are each consuming client's job.
- **Owning RF acquisition or radiod I/O.** That is `ka9q-python`; this library is
  pure analysis given samples/phasors a client already has.
- **Bundling licence-restricted engines.** PHaRLAP (DST-restricted) is never
  shipped; the `raytrace` wrapper is a no-op stub until it is staged out-of-band.
- **Per-client policy** (thresholds, channel plans, retention) — the library
  provides math; clients own the parameters they pass in.

## 4. Stakeholders & actors (consuming components)

This library has no operators; its "actors" are the components that import it.

- **superdarn-sounder** — greenfield consumer of `timing` (AuthorityReader),
  `geometry`, `propagation`; the validating case for the API.
- **hf-timestd** — consumes `geometry` heavily (the ~17 great-circle copies
  collapsing here), plus `propagation`/`constants`/`ionosphere.solar`; the
  *source* of the canonical timing/SNR/carrier-dTEC math. Also the **producer**
  of the `authority.json` this library reads.
- **codar-sounder** — consumes `geometry` and `propagation`; source of the
  oblique-inversion and scintillation physics; still carries a local
  AuthorityReader copy (pending migration).
- **hf-tec** — source of `dsp.CoherentStack` and percentile noise-floor; still
  carries a local AuthorityReader and does not yet declare the dep.
- **psk-recorder / wspr-recorder** — pure `AuthorityReader` consumers; both still
  carry local copies and do not yet declare the dep.
- **Optional heavy deps:** `iri2020` (Fortran), `pylap`/PHaRLAP (DST-licensed),
  `apexpy` — gated behind extras; absent → documented degradation.
- **The suite build chain** — `uv sync` + `[tool.uv.sources] editable = true`,
  which is how every consumer pins this library (sigmond fleet-upgrade pattern).

## 5. Assumptions & constraints

- `DSP-C-001` `[DOC]` ✅ The library SHALL be **importable-only** — no CLI, no
  systemd, no client-contract surface — and pinned editable from a sibling
  checkout (`[tool.uv.sources] hamsci-dsp = { path = "../hamsci-dsp", editable = true }`).
- `DSP-C-002` `[CODE]` ✅ `hamsci_dsp.timing` and `hamsci_dsp.constants` SHALL be
  **stdlib-only**, importable with zero third-party deps (so the §18 reader works
  in a minimal client).
- `DSP-C-003` `[DOC]` ✅ The numeric core (`geometry`, `dsp`, `propagation`) SHALL
  depend only on `numpy>=1.24` and `geographiclib>=2.0` — light and universal.
- `DSP-C-004` `[DOC]` ✅ Heavy scientific engines (`ionosphere`→`iri2020`,
  `raytrace`→`pylap`/PHaRLAP, `geomag`→`apexpy`) SHALL be **optional extras**,
  never required by the core import path.
- `DSP-C-005` `[CODE]` ✅ Python ≥3.10.
- `DSP-C-006` `[DOC]` ✅ The `authority.json` **schema is owned upstream**
  (hf-timestd METROLOGY §4.5.2); this library tracks it as a consumer and SHALL
  NOT redefine it.
- `DSP-C-007` `[DOC]` ✅ Each module SHALL be extracted **math-identical** from the
  client whose review made it canonical (provenance named in the module
  docstring), so migration is a behaviour-preserving move, not a rewrite.

## 6. Functional requirements

### 6.1 Timing-authority consumer (the §18 consumer side — load-bearing)
- `DSP-F-001` `[DOC]` ✅ SHALL provide `AuthorityReader.read()` that atomically
  reads `/run/hf-timestd/authority.json` and returns an `AuthoritySnapshot`, or
  `None` on any error (missing file, bad JSON, OS error) — so "file missing" is
  indistinguishable from "hf-timestd not running."
- `DSP-F-002` `[CODE]` ✅ `read()` SHALL reject snapshots whose `schema` is not in
  the supported set (`{"v1"}`) and whose `utc_published` is older than
  `freshness_sec` (default 60 s), returning `None`.
- `DSP-F-003` `[CODE]` ✅ `AuthoritySnapshot` SHALL expose `offset_usable` (active
  tier present AND `rtp_to_utc_offset_ns` present) and `offset_seconds`, so a
  consumer can gate on whether a concrete offset is applicable.
- `DSP-F-004` `[DOC]` ✅ SHALL provide `AuthoritySnapshot.to_timing_authority(client_radiod)`
  emitting the canonical timing-provenance block stamped into every client's data
  records (`source`, `schema`, `a_level`, `t_level_active`, `t_level_witnesses`,
  `rtp_to_utc_offset_ns`, `sigma_ns`, `disagreement_flags`, `governor_radiod`,
  `client_radiod`, `authority_utc_published`).
- `DSP-F-005` `[DOC]` ✅ SHALL provide `standalone_timing_authority(client_radiod)`
  returning a **shape-identical** provenance block (`source="standalone-fallback"`,
  null offset) so a record's key is uniform whether or not the authority is present.
- `DSP-F-006` `[CODE]` ✅ The reader SHALL accept an injectable `now_fn` and `path`
  for testability and non-default deployment.

### 6.2 Constants
- `DSP-F-010` `[DOC]` ✅ SHALL define the shared physical constants in one place —
  `C_M_S`/`C_KM_S`/`C_KM_MS`, `K_TEC=40.3`, `TECU=1e16`, `R_EARTH_KM`/`R_EARTH_M` —
  replacing the per-client redefinitions (in differing unit forms).

### 6.3 Geodesy & path geometry
- `DSP-F-020` `[DOC]` ✅ SHALL provide WGS-84 geodesics via geographiclib:
  `great_circle_km`, `bearing_deg`, `midpoint`, `destination` — the single home
  for the great-circle math reimplemented 19+ times.
- `DSP-F-021` `[CODE]` ✅ SHALL provide spherical-Earth reflection geometry —
  `elevation_angle_deg`, `max_single_hop_distance_km`, `n_hops_for_distance`,
  `hop_geometry` (→ `HopGeometry` with `geometric_delay_ms`), and its inverse
  `height_from_path` — by law-of-cosines, superseding the older flat-segment
  approximation.
- `DSP-F-022` `[CODE]` ✅ SHALL provide Maidenhead `grid_to_latlon` /
  `latlon_to_grid` (4- and 6-char).

### 6.4 DSP primitives
- `DSP-F-030` `[DOC]` ✅ SHALL provide canonical peak-SNR — `peak_snr_db_envelope`
  (Rayleigh) and `peak_snr_db_signed` (signed-Gaussian) with `rayleigh_envelope_sigma`
  — verbatim from hf-timestd `core/snr.py`.
- `DSP-F-031` `[DOC]` ✅ SHALL provide a robust `noise_floor(method=median|percentile|mad)`
  + `mad`, unifying the median floor (codar/superdarn) and 30th-percentile floor
  (hf-tec).
- `DSP-F-032` `[CODE]` ✅ SHALL provide carrier-phase→Doppler (`unwrap_phase`,
  `doppler_from_phase`, `doppler_from_phase_slope`) and `fft_correlate`.
- `DSP-F-033` `[DOC]` ✅ SHALL provide `CoherentStack` (slow-time range-Doppler
  integration) + `doppler_axis_hz`, from hf-tec `core/coherent.py`.

### 6.5 Propagation observables
- `DSP-F-040` `[DOC]` ✅ SHALL compute carrier-phase dTEC + dTEC/dt
  (`dtec_from_phase`→`CarrierDTEC`) directly from phase with cycle-slip/gap
  coasting and an unwrap-quality score — math-identical to hf-timestd
  `core/carrier_tec.py`.
- `DSP-F-041` `[DOC]` ✅ SHALL provide oblique-sounding inversion — `virtual_height_km`,
  `equivalent_vertical_freq_mhz`, `oblique_muf_mhz`, `obliquity_factor`,
  `takeoff_zenith_deg`, `classify_layer`, `slant_to_vertical_tec`,
  `group_delay_to_tec`, and the matching `*_uncertainty_*` — from codar/hf-timestd.
- `DSP-F-042` `[DOC]` ✅ SHALL compute scintillation indices (`compute_scintillation`
  → `ScintillationResult`: S4 amplitude, σφ phase) under selectable conventions
  (`ITU_R_LBAND`, `HF_OBLIQUE`) with `reclassify`, from codar `scintillation.py`.

### 6.6 Optional heavy engines (extras)
- `DSP-F-050` `[DOC]` ✅ SHALL provide dep-free solar geometry (`solar_position`,
  `solar_zenith_angle`) and `ionosphere_state` that uses IRI when the `iono` extra
  is installed and SHALL **fall back to a parametric tier** otherwise (never hard-fail).
- `DSP-F-051` `[DOC]` ✅ SHALL provide a lazy `RaytraceEngine` whose `is_available()`
  gates a PyLAP/PHaRLAP trace and which returns `[]` (no-op) when the engine is
  absent — advisory overlay only.
- `DSP-F-052` `[CODE]` 🟡 `RaytraceEngine.compute_modes` SHALL ray-trace IRI-backed
  modes where PHaRLAP is staged; the trace **wiring is not in this library** (it
  raises `NotImplementedError` when available-but-unwired). *(gap — `DSP-F-093`.)*

### 6.7 De-duplication migration (the library's reason for being)
- `DSP-F-060` `[DOC]` 🟡 Every extracted module SHALL have its client duplicates
  retired. **State at v0.2:** superdarn-sounder consumes timing/geometry/propagation;
  hf-timestd consumes geometry/propagation/constants/solar. **Still duplicated:**
  the four `AuthorityReader` copies (codar, hf-tec, psk, wspr) and hf-timestd's
  local `snr.py`/`carrier_tec.py`/`tec_geometry.py`. *(epic — `DSP-F-090`/`091`.)*

## 7. Quality / non-functional requirements

- `DSP-Q-001` `[CODE]` ✅ `AuthorityReader.read()` SHALL **never raise** — every
  error path returns `None` — so a consumer's frame loop cannot be killed by a
  malformed/half-written authority file.
- `DSP-Q-002` `[CODE]` ✅ The reader SHALL treat `authority.json` as read-whole-or-
  not-at-all (paired with the producer's atomic overwrite, `HFT-Q-004`); a torn
  read degrades to `None`, not a partial snapshot.
- `DSP-Q-003` `[DOC]` ✅ The core import (`timing`, `constants`) SHALL pull **zero**
  third-party packages; numeric core only numpy+geographiclib; heavy engines only
  via extras (verifiable by importing in a stdlib-only venv).
- `DSP-Q-004` `[CODE]` ✅ Optional engines SHALL degrade gracefully — absent IRI →
  `tier=parametric`; absent PyLAP → `is_available()=False`, empty trace — never a
  hard failure of a consumer.
- `DSP-Q-005` `[CODE]` ✅ Each public module SHALL have unit tests (timing 7,
  geometry 9, dsp 8, propagation 10, scintillation 5, ionosphere/raytrace 4) that
  ARE the behaviour-preservation guarantee for the extraction.
- `DSP-Q-006` `[NEW]` 🟡 The extraction SHALL be **provably math-identical** to the
  client copy it replaces (golden-vector parity test against the donor client),
  not merely "tested in isolation." Today only in-library unit tests exist; no
  cross-repo parity gate. *(gap — `DSP-Q-007`.)*
- `DSP-Q-008` `[NEW]` ⬜ Public API stability SHALL be governed by an explicit
  policy (semver: additive within a minor, breaking only on a major) and a
  documented public surface, since consumers pin `>=0.2`. Not yet written. *(gap.)*

## 8. External interfaces

### 8.1 Inputs (consumed)
- `authority.json` at `/run/hf-timestd/authority.json` (schema `v1`) — the only
  filesystem input, read by `AuthorityReader`.
- In-memory data the caller already holds: IQ / phasor arrays, phase time-series,
  epochs, frequencies, lat/lon, group/ground ranges. No RF, no radiod, no sockets.
- Build-time deps: `numpy`, `geographiclib`; optional extras `iri2020` (needs
  gfortran), `pylap`+PHaRLAP (DST-staged), `apexpy`.

### 8.2 Outputs (produced)
- Pure return values — dataclasses (`AuthoritySnapshot`, `HopGeometry`,
  `CarrierDTEC`, `ScintillationResult`, `IonoState`, `RayMode`) and numpy arrays /
  floats / dicts. No files, no sink writes, no logs beyond `logger.debug` on the
  reader's swallowed errors.
- The **canonical timing-provenance dict** (`to_timing_authority` /
  `standalone_timing_authority`) that consumers embed verbatim in their data records.

### 8.3 Contracts / APIs — the public Python API (the client contract does NOT apply)
This is a **library**: there is no sigmond↔client contract conformance level, no
`inventory`/`validate`, no control socket. The "interface" is the importable API,
and its stability is what consumers depend on.

- `DSP-I-001` `[DOC]` ✅ **The public API is the contract.** The stable surface is
  the named modules and their exported symbols: `timing.{AuthorityReader,
  AuthoritySnapshot, standalone_timing_authority, DEFAULT_PATH, DEFAULT_FRESHNESS_SEC}`;
  `constants.*`; `geometry.*`; `dsp.*`; `propagation.*` (the `__all__` list);
  `ionosphere.{solar_*, ionosphere_state, IonoState}`; `raytrace.{RaytraceEngine,
  RayMode}`. Consumers pin `hamsci-dsp>=0.2.0` editable.
- `DSP-I-002` `[DOC]` ✅ **§18 consumer side lives here.** `AuthorityReader` +
  `to_timing_authority` ARE the contract §18 *consumer* implementation that every
  RF client uses to read hf-timestd's authority and stamp provenance; the
  *producer* obligations are hf-timestd's (`HFT-I-002`), the *schema* is METROLOGY
  §4.5.2. This library restates neither — it implements the read side once.
- `DSP-I-003` `[CODE]` ✅ The `to_timing_authority` / `standalone_timing_authority`
  dicts SHALL be **shape-stable** across both states and across all clients (a
  schema-versioned `"schema":"v1"` block), so downstream sink schemas can rely on
  the provenance key.
- `DSP-I-004` `[NEW]` ⬜ A written **API-stability / deprecation policy** (semver +
  changelog of the public surface) is owed, since five-plus repos pin this library
  and a silent rename would break them all (`DSP-Q-008`).

## 9. Data requirements

No persistent data, no schema ownership, no retention — the library holds **no
state** and writes nothing. The one external data *shape* it depends on is the
`authority.json` v1 record (owned by hf-timestd METROLOGY §4.5.2); the one data
shape it *defines* for downstream use is the timing-provenance block
(§8.2 / `DSP-I-003`), which becomes a column/JSON key in each consumer's records
(e.g. superdarn `timing_authority`). Reference constants (`K_TEC`, `R_EARTH_KM`,
…) are the only "data" it ships, and they are physical constants, not config.

## 10. Dependencies & development sequence

**Runtime deps:** `numpy>=1.24`, `geographiclib>=2.0` (numeric core);
**extras** — `iono`→`iri2020>=1.7` (+gfortran), `raytrace`→`pylap` (+PHaRLAP
out-of-band), `geomag`→`apexpy>=2.0`; `dev`→`pytest`. No runtime dep on any
sigmond client (the dependency arrow points *into* this library, never out).

**Development sequence (intended, recovered as requirement):**
- **v0.1** (`45f0ee1`) — establish the library: extract `timing` (the §18 reader,
  the highest-leverage duplicate), `constants`, `geometry`, and the first `dsp`
  primitives. superdarn-sounder built against it from the start (validating the
  API at the consumer end).
- **v0.2** (`24ee5bc`/`8b0def7`/`d53e400`) — grow into the shared
  **propagation-analysis** library: carrier-dTEC, oblique inversion, scintillation
  (with spherical-hop geometry + scintillation-convention conventions), optional
  `ionosphere`/`raytrace`/`geomag` engines behind extras.
- **Ongoing — the #18 dedup migration:** rewire existing clients off their local
  copies opportunistically as each module is next touched. Done: hf-timestd
  geometry; superdarn (greenfield). Pending: the four AuthorityReader copies,
  hf-timestd snr/carrier_tec/tec_geometry, codar invert/scintillation, hf-tec
  detect/coherent.
- **Future:** PyLAP trace wiring (`DSP-F-052`), API-stability policy
  (`DSP-Q-008`), cross-repo parity gate (`DSP-Q-006`).

## 11. Acceptance criteria & verification

- API/extraction correctness → `uv run pytest` (43 tests across 6 files);
  green is the behaviour-preservation acceptance check for each extracted module.
- Stdlib-core constraint (`DSP-C-002`/`DSP-Q-003`) → import `hamsci_dsp.timing`
  and `hamsci_dsp.constants` in a venv with neither numpy nor geographiclib; SHALL
  succeed.
- Graceful-degradation (`DSP-Q-004`) → `ionosphere_state` returns `tier=parametric`
  without `iri2020`; `RaytraceEngine().is_available()` is `False` and
  `compute_modes()==[]` without PyLAP (covered by `test_ionosphere_raytrace.py`).
- §18 consumer correctness (`DSP-F-001..005`) → `test_timing.py`: missing file →
  `None`; stale/unsupported-schema → `None`; provenance dict shape matches between
  `to_timing_authority` and `standalone_timing_authority`.
- Migration progress (`DSP-F-060`) → `grep -rl "class AuthorityReader"` across the
  suite trends to **zero** copies outside hamsci-dsp; per-client `pyproject`
  declares `hamsci-dsp` and the local module is deleted.
- Math-identity (`DSP-Q-006`, owed) → golden-vector parity test vs the donor
  client before its copy is deleted.

## 12. Risks & open questions

- `DSP-F-090` `[NEW]` 🟡 **AuthorityReader still quadruplicated.** codar-sounder,
  hf-tec, psk-recorder, wspr-recorder each carry a local
  `…/authority_reader.py`; hf-tec/psk/wspr do not even declare the `hamsci-dsp`
  dep yet. A §18 schema/freshness fix today must be made in five places. Highest-
  value migration item. *(#18 hamsci-dsp dedup epic.)*
- `DSP-F-091` `[NEW]` 🟡 **hf-timestd donor modules not yet retired.** Its local
  `core/snr.py`, `core/carrier_tec.py`, `core/tec_geometry.py` remain even though
  the canonical copies now live here; geometry migrated, these did not. Drift risk
  until deleted. *(#18 dedup epic.)*
- `DSP-F-092` `[NEW]` ⬜ **codar/hf-tec partial migration.** codar consumes
  geometry/propagation but keeps its own AuthorityReader and `invert`/
  `scintillation`; hf-tec's `detect`/`coherent` are the donor for `dsp` but not yet
  consuming it. Finish the round-trip. *(#18 dedup epic.)*
- `DSP-F-093` `[NEW]` 🟡 **Raytrace wiring stubbed.** `compute_modes` raises
  `NotImplementedError` even when PyLAP imports; the trace lives in hf-timestd
  `core/raytrace_engine.py`, not here. Either port the wiring or document the
  wrapper as availability-probe-only.
- `DSP-Q-006` `[NEW]` 🟡 **No cross-repo parity gate.** Extractions are claimed
  math-identical but only in-library unit tests exist; nothing proves the library
  result equals the donor client's before its copy is deleted.
- `DSP-Q-008`/`DSP-I-004` `[NEW]` ⬜ **No written API-stability policy** though
  five-plus repos pin `>=0.2`; a silent public-symbol rename breaks the fleet.
- Version-pin skew: hf-timestd/codar/superdarn declare `hamsci-dsp>=0.2.0`;
  wspr/psk/hf-tec declare nothing — confirm and align as part of `DSP-F-090`.

## 13. Traceability

| Requirement | #18 issue | Verification | PSWS #6 |
|---|---|---|---|
| DSP-I-002 / DSP-F-001..005 (§18 consumer) | hamsci-dsp dedup epic | `test_timing.py` | #6:50 (timing tiering) |
| DSP-F-090 (AuthorityReader ×4 dup) | *(new — file: hamsci-dsp dedup)* | `grep AuthorityReader` → 0 | #6:50 |
| DSP-F-091 (hf-timestd snr/tec dup) | *(new — file: hamsci-dsp dedup)* | donor copy deleted | — |
| DSP-F-092 (codar/hf-tec partial) | *(new — file: hamsci-dsp dedup)* | per-client dep + delete | #6:31 (sensor integ.) |
| DSP-F-040 (carrier dTEC) | Clients: hf-timestd / hf-tec | `test_propagation.py` | #6:19 (Doppler API) |
| DSP-F-093 (raytrace wiring) | *(new — file)* | trace vs hf-timestd | — |
| DSP-Q-006 (parity gate) | *(new — file)* | golden-vector cross-repo | — |
| DSP-Q-008 / DSP-I-004 (API policy) | *(new — file)* | published policy + changelog | — |

*New rows (DSP-F-090/091/092/093, DSP-Q-006, DSP-Q-008) are this review's surfaced
gaps; promote DSP-F-090/091/092 to the #18 hamsci-dsp dedup migration epic.*
