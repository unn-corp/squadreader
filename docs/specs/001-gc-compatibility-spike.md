# SPEC — GC Maps / SquadReader Compatibility Spike

**Status:** Draft  
**Version:** 0.1  
**Date:** 2026-08-25  

GC is treated as a non-commercial Steam Workshop mod, and this project is non-commercial. Asset monetization is outside this spike. SquadReader source-license obligations remain separate.

## Why

GC Maps needs an evidence-based answer to whether SquadReader can observe a live Galactic Contention server and whether GC Maps can supply accurate runtime identifiers, map metadata, faction data, and assets. This spike produces that answer from one pinned server build before production integration.

## Capabilities

CAP-001 — Maintainer can determine whether one pinned GC server build is readable.

  ↳ Test: Start the designated build and record `supported`, `unsupported`, or `failed` with a specific reason.

CAP-002 — Maintainer can enumerate exact runtime identifiers for GC vehicles, kits, weapons, deployables, factions, and layers.

  ↳ Test: Run a controlled fixture containing each category and export raw identifiers exactly as observed.

CAP-003 — Maintainer can map observed runtime identifiers to canonical GC Maps records.

  ↳ Test: Every fixture identifier resolves to a canonical record or explicit `unmapped` / `ambiguous` state. No guessed classification passes.

CAP-004 — Maintainer can associate an observed layer with correct GC Maps imagery and metadata.

  ↳ Test: Validate one complete layer and one partially catalogued layer. Correct imagery must resolve; unavailable fields must be reported.

CAP-005 — Maintainer can generate a versioned compatibility manifest.

  ↳ Test: Manifest records server/build identity, raw identifiers, canonical mappings, asset references, coverage status, and provenance.

CAP-006 — Maintainer can compare later extraction results against the previous manifest.

  ↳ Test: Changed source build or asset set produces a reviewable added/removed/changed/unmapped diff.

CAP-007 — Operator can run the spike without exposing live player or replay data publicly.

  ↳ Test: Unauthenticated access is denied and test data remains confined to the controlled environment.

## Constraints

- First validation targets one pinned GC dedicated-server build and one reader instance.
- Reader and server run on the same Linux host with required process-memory permissions.
- First fixture covers vehicles, kits, weapons, deployables, factions, players, and layers.
- Raw runtime identifiers remain separate from canonical GC Maps identifiers.
- Unknown, unavailable, and unsupported data remain explicit states.
- Capture points must not be presented as accurate zone geometry without source evidence.
- Raw `.pak`, `.utoc`, and `.ucas` inputs are not committed.
- Every generated record includes source build and asset provenance.
- Production live-server integration is blocked until this spike passes.

## Non-goals

- Supporting every GC or Squad version.
- Building the complete live map, replay, statistics, or ELO product.
- Extracting every GC icon before runtime compatibility is proven.
- Reconstructing missing capture-zone geometry by estimation.
- Supporting multiple servers or public deployment.
- Replacing GC Maps' existing catalog and extraction workflow.

## Success Signal

SS-1: One designated GC build produces valid live output for 100% of required fixture categories.

SS-2: 100% of observed fixture identifiers are correctly mapped or explicitly marked unmapped, with zero silent fallback classifications.

SS-3: At least two GC layers resolve to correct imagery and report metadata coverage accurately, including unavailable fields.
