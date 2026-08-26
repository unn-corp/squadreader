# SPEC — GC Map/Layer Coverage Verification

**Status:** Implemented  
**Version:** 0.1  
**Date:** 2026-08-26

## Why

GC contains many map variants, and incomplete extraction data can make a replay appear healthy while its map is missing, mis-scaled, or attached to the wrong layer. Operators need a fail-closed answer for each configured layer and separate evidence for layers observed at runtime.

## Capabilities

CAP-001 — Operator can identify each configured layer as render-ready or incomplete, with a specific failure category.
  ↳ Test: Run audit against fixtures containing valid, missing, malformed, and unavailable layer data.

CAP-002 — Operator can confirm that a layer alias resolves to its exact map identity, or is rejected when identity is ambiguous.
  ↳ Test: Run audit against duplicate aliases and exact layer variants with conflicting bounds.

CAP-003 — Operator can inspect runtime captures for observed layers, provider selection, and exact runtime identifiers without bindings.
  ↳ Test: Run audit against captures containing mod and vanilla frames plus role, vehicle, deployable, marker, and weapon identifiers.

CAP-004 — Release validation can fail when strict map/layer coverage is incomplete.
  ↳ Test: Run strict audit against incomplete and complete catalogs and verify exit status.

## Constraints

- Never invent world coordinates, imagery, or layer identity.
- Reuse bounds only when one exact `mapId` has one authoritative bounds tuple.
- Treat ambiguous aliases and unobserved runtime identifiers as unresolved.
- Preserve vanilla fallback behavior when a mod provider lacks an exact asset binding.

## Non-goals

- Extracting missing Unreal packages or textures.
- Proving runtime coverage for classes absent from supplied captures.
- Replacing authored map/layer relationships with name heuristics.

## Success Signal

SS-1: Strict audit exits successfully only when every configured layer has valid bounds, imagery, and a serving file.

SS-2: Audit report lists every incomplete layer and groups failures by category.

SS-3: Runtime report lists every observed layer and every observed identifier lacking an exact provider binding.
