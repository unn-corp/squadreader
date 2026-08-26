# GC Maps Extraction Pattern Traceability

**Status:** Draft  
**Version:** 0.1  
**Date:** 2026-08-26  

Audit basis: GC Maps `AGENTS.md`, `docs/MECHANISM.md`, `docs/MAP-DATA.md`, `tooling/ue_zen.py`, `tooling/extract_map_catalog.py`, `tooling/extract_roles.py`, `tooling/extract_vehicle_counts.py`, `tooling/extract_vehicle_delays.py`, `tooling/extract_layer_setups.py`, `tooling/build_changelog.py`, and `tooling/test_map_catalog.py`.

## Adopted patterns

| GC Maps pattern | Evidence | SquadReader extraction requirement | Verification |
|---|---|---|---|
| One shared UE5 reader | All structured extractors import `ue_zen.py` and `build_index()` | Reuse one structured-package reader; do not add a second parser | Import/dependency check plus package fixture parity |
| Tagged-property boundary | `ue_zen.py` rejects `PKG_UnversionedProperties` instead of guessing | No `.usmap`/`global.utoc` dependency; fail explicitly on unsupported format | Fixture with unsupported package flag |
| Exact package identity | `find_layer_package()` matches complete package stem and `/GLD/` path | Exact package paths are authoritative; near matches fail | `V1` vs `V10` negative test |
| Relationship over proximity | Vehicle counts resolve setup → `LimitedCount` → `BaseAvailability` | Resolve object references and target properties; never use nearby strings | Known reference-chain fixture |
| Explicit audited override | `LAYER_MAP_OVERRIDES` uses complete layer IDs | Overrides require complete IDs, review, provenance, and field scope | Override supplies imagery only |
| Source fingerprinting | `extract_map_catalog.py::source_fingerprint()` hashes ordered source files | Pin server/client/game inputs and record source fingerprint in every manifest | Same input → same fingerprint; changed package → changed fingerprint |
| Deterministic outputs | Stable sorting, schema versions, generated artifacts | Stable output ordering and schema version; no hand-edited generated files | Re-run diff is empty for unchanged inputs |
| Stage then replace | Map catalog writes a temp file and uses `os.replace()` after validation | Build in staging; atomically promote only after verification | Inject failure and confirm last-known-good remains |
| Fail closed | Extractors abort on missing dirs, empty index, zero decoded layers, zero profiles | Required extraction failure is non-zero and blocks promotion | Empty/missing source fixtures |
| Visible uncertainty | `measured` / `partial` / `unavailable`; per-category reasons | Preserve coverage and failure reasons; never turn missing data into zero/empty truth | Invalid catalog-row fixtures |
| Separate point certainty | `active` vs `possible`; exact frame required for reuse | Do not copy coordinates/phases across unproven layer frames | Randomized-layer fixture |
| Source separation | Server paks, game paks, and client paks are separate inputs | Keep structured server/game extraction separate from client texture decode | Source-group manifest validation |
| Narrow texture selection | Tactical map textures preferred; generic HUD/loading assets excluded | Request-driven category allowlist; no full texture dump into public assets | Candidate-selection fixture |
| Independent verification | `verify_pools.py` re-derives critical rules without importing generator state | Add verifier that does not import generator mappings/constants for critical checks | Mutation test against generator output |
| Negative-case tests | `test_map_catalog.py` tests exact matching, invalid coverage, bounds, and bad texture input | Every adapter rule gets a positive and near-match/invalid fixture | Test matrix in compatibility report |
| Safe public projection | `build_changelog.py` uses explicit `PRIVATE` and export allowlists | Raw packages, secrets, recordings, and unreviewed assets cannot enter public output | Public-output manifest audit |
| Vendored derived data | GC Maps vendors outputs so `/tmp` loss cannot silently empty scans | Commit only approved derived manifests/assets; runtime generation may use scratch but cannot depend on it | Delete scratch and rerun consumer validation |

## Required implementation shape

The extraction work must preserve this data flow:

```text
local server/game/client packages
  → source manifest + fingerprint
  → shared IoStore/package reader
  → exact package/reference inventory
  → decoded canonical catalogs and selected textures
  → reviewed runtime mapping manifest
  → staged SquadReader adapter
  → independent verification
  → atomic promotion
```

Runtime names and package identities must remain separate until live reader evidence joins them. Package extraction can identify `GAR_LAAT` as a canonical vehicle record; only the live server test can prove whether the reader emits `GAR_LAAT`, `BP_..._C`, or another runtime value.

## Spec changes applied

These controls are now required in [004-local-asset-extraction-and-test-build.md](./004-local-asset-extraction-and-test-build.md):

- shared `ue_zen.py` reader and tagged-property boundary;
- exact identity and object-reference resolution;
- source-group fingerprints and deterministic manifests;
- explicit coverage and point-certainty states;
- staged atomic promotion with last-known-good preservation;
- independent verification and negative fixtures;
- client-only texture decoding boundary;
- public-output allowlist and raw-input exclusion.
