# Live GC Server Validation Plan

**Status:** Draft  
**Version:** 0.1  
**Date:** 2026-08-25  

## Objective

Prove or reject SquadReader compatibility with one controlled GC dedicated-server build. Test reader correctness before frontend or production integration.

## Test environment

- Linux host.
- One pinned GC server/mod build.
- Matching client asset revision for extraction.
- SquadReader fork at a recorded commit.
- Process-memory permissions configured for the test account.
- Private network access only.
- Test output stored outside public web assets.

Record before each run:

- SquadReader commit.
- Server executable/build identity.
- GC mod revision.
- Client asset revision.
- GC Maps catalog revision.
- Map and layer selected.
- Reader configuration and permission mode.

## Fixture matrix

| Fixture | Required observation | Pass condition |
|---|---|---|
| Server identity | Build and process identity | Reader reports expected build context |
| Map/layer | Exact layer and map identity | Correct map image resolves; layer status is explicit |
| Teams/factions | Team IDs and faction IDs | Both sides map to canonical GC factions |
| Players | Player identity, team, role | Required fields read without corruption |
| Kits/roles | Exact runtime role or kit name | Raw name exported and canonical match reviewed |
| Weapons | Exact runtime weapon/class name | Raw name exported and category preserved |
| Vehicles | Vehicle class, faction, kind | Vehicle maps to one canonical record or explicit unresolved state |
| Deployables | Deployable class and owner/team | Raw name and ownership fields captured |
| Capture zones | Position and available geometry | Geometry only accepted when source-backed |
| Recording | Snapshot and position continuity | Recording opens and contains expected event sequence |

## Run sequence

1. Start pinned server with one known GC layer.
2. Confirm process identity and reader permissions.
3. Start SquadReader in private test mode.
4. Join with controlled test clients or use a brief live match.
5. Exercise each fixture category.
6. Capture runtime inventory and recording output.
7. Compare observations with GC Maps catalogs.
8. Generate compatibility and mapping manifests.
9. Repeat with second layer selected for partial-data coverage.
10. Produce pass/fail report and preserve artifacts.

## Failure classification

| Failure | Meaning | Next action |
|---|---|---|
| Process cannot be read | Permission, host, or reader startup failure | Fix environment; rerun |
| Reader starts but fields are corrupt | Offset or object-layout incompatibility | Stop integration; investigate build compatibility |
| Fields read but names are unknown | GC catalog/mapping gap | Extend inventory and adapter |
| Layer resolves incorrectly | Layer alias or catalog mismatch | Fix exact mapping; reject fuzzy fallback |
| Image resolves but coordinates fail | Incomplete map source data | Expose coverage state; do not infer |
| Recording fails or grows unexpectedly | Format, performance, or storage issue | Measure and set operational limits |
| Frontend shows wrong asset | Manifest, naming, or fallback mismatch | Fix asset mapping before UI integration |

## Go/no-go rules

### Go

- Required fixture categories are readable.
- Runtime identifiers are stable across repeated observations.
- Mappings are explicit and reviewable.
- At least two layers resolve correctly.
- No silent wrong-map, wrong-faction, or wrong-vehicle output exists.

### No-go

- Reader depends on unverified offsets for the pinned build.
- Required categories are silently missing or misclassified.
- Layer fallback can select an incorrect map.
- Capture geometry is fabricated from points.
- Private test data can be reached without authorization.
