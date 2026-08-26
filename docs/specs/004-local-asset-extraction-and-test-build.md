# SPEC — Local GC Asset Extraction and Live Test Build

**Status:** Draft  
**Version:** 0.1  
**Date:** 2026-08-25  
**Repositories:** `unn-corp/squadreader`, `unn-corp/gc-maps`  

## Why

SquadReader needs GC-specific metadata and assets, while GC Maps already has local Unreal package tooling that can provide much of that data. This work defines a reproducible extraction pipeline and a minimum live-server test build that proves package extraction, runtime observation, identifier mapping, and asset serving as separate gates.

## Capabilities

CAP-001 — Maintainer can declare and fingerprint one local GC/Squad asset installation.

  ↳ Test: Given explicit server-mod, client-mod, and base-game package directories, the tool validates required files, records a stable source fingerprint, and fails before extraction when a required input is missing.

### Source contract

Required inputs are explicit command-line paths or equivalent configuration:

```text
--mod-server-paks  <GC>/Content/Paks/LinuxServer
--mod-client-paks  <GC>/Content/Paks/Windows
--game-paks       <Squad>/SquadGame/Content/Paks
--output          <artifact-root>
```

The pipeline must not search arbitrary disks or assume one Steam installation path. Source manifest records package filenames, sizes, and hashes, but not machine-specific absolute paths.

`source-manifest.json`:

```json
{
  "schemaVersion": 1,
  "sources": {
    "modServer": {"label": "gc-server", "fileCount": 0},
    "modClient": {"label": "gc-client", "fileCount": 0},
    "game": {"label": "squad-game", "fileCount": 0}
  },
  "fingerprint": "<sha256>",
  "generatedAt": "<UTC timestamp>",
  "toolRevision": "<git commit>"
}
```

CAP-002 — Maintainer can index and extract exact Unreal assets from local IoStore containers.

  ↳ Test: Request a known package path, extract it from paired `.utoc` / `.ucas` files, and verify byte count, package identity, and deterministic output.

### Extraction contract

Extend GC Maps' existing package reader and extractors rather than creating a second container implementation:

- IoStore directory indexing: [`tooling/ue_zen.py`](https://github.com/unn-corp/gc-maps/blob/main/tooling/ue_zen.py).
- Named raw extraction: [`tooling/extract_assets.py`](https://github.com/unn-corp/gc-maps/blob/main/tooling/extract_assets.py).
- Oodle decompression: existing `oozdec` prerequisite.
- Structured package decoding: existing role, map, vehicle, and setup extractors.

Raw staging layout is outside tracked source:

```text
<artifact-root>/
  source-manifest.json
  raw/
  inventory/
  decoded/
  generated/
  reports/
```

Required behavior:

- Exact package paths are authoritative.
- Filename substring search may discover candidates but cannot establish identity.
- Required extraction failures return non-zero and write a failure record.
- Best-effort inventory may continue, but unresolved records remain visible.
- Raw package bytes never enter Git, generated web assets, or test recordings.

`extraction-report.json` records each request as `extracted`, `missing`, `decode_failed`, or `skipped`, with package path, source group, error, and tool revision.

CAP-003 — Maintainer can decode selected map and gameplay textures into approved derived assets.

  ↳ Test: Decode one tactical map texture, one vehicle icon, one kit icon, one weapon icon, and one deployable icon; verify output dimensions, alpha behavior, source identity, and manifest entries.

### Texture contract

Use request-driven decoding. Do not scan every texture into the public asset directory.

`texture-requests.json`:

```json
{
  "schemaVersion": 1,
  "sourceFingerprint": "<sha256>",
  "requests": [
    {
      "assetPath": "/ANE_BASE/Maps/Yavin/Minimap/GC_Yavin4_Minimap",
      "category": "map",
      "canonicalId": "yavin",
      "required": true,
      "format": "webp"
    }
  ]
}
```

Texture decoding uses the existing CUE4Parse helper boundary:

- [`tooling/cue_texture_exporter/Program.cs`](https://github.com/unn-corp/gc-maps/blob/main/tooling/cue_texture_exporter/Program.cs) loads exact `UTexture` packages.
- The map catalog extractor already handles client texture requests and WebP rendering.
- New icon extraction must reuse the same request/result model.

Output layout:

```text
generated/assets/
  maps/<map-id>.webp
  vehicles/<canonical-id>.webp
  kits/<canonical-id>.webp
  weapons/<canonical-id>.webp
  deployables/<canonical-id>.webp
```

`asset-manifest.json` records canonical ID, category, source package path, output path, dimensions, format, alpha presence, source fingerprint, extraction status, and fallback asset.

Texture decode errors must distinguish missing package, missing export, unsupported pixel payload, decode failure, and render failure. A placeholder may be used by the test viewer only when the manifest marks the asset unresolved.

CAP-004 — Maintainer can generate canonical GC catalogs without confusing package names with live runtime names.

  ↳ Test: Generate vehicle, kit, weapon, deployable, faction, and layer records; each record retains source package identity and has a separate runtime-mapping status.

### Catalog contract

Reuse existing GC Maps outputs where available:

- `map_catalog.json` for map/layer imagery, points, bounds, and coverage.
- `factions.json` and `vehicles.json` for canonical faction/vehicle records.
- `roles.json` for kit/role records.
- Setup and loadout extractors for vehicle availability and references.

Add extractors where current catalogs do not expose required records:

- Weapon inventory references from role/loadout assets.
- Deployable class and ownership references from role/loadout assets.
- Explicit icon asset references for each canonical record.

Every catalog record has:

```json
{
  "canonicalId": "GAR_LAAT",
  "category": "vehicle",
  "displayName": "LAAT Gunship",
  "assetPath": "/ANE_BASE/Vehicles/...",
  "factionIds": ["GAR"],
  "runtimeNames": [],
  "mappingStatus": "unobserved",
  "source": {
    "sourceFingerprint": "<sha256>",
    "packagePath": "<exact package path>"
  }
}
```

`runtimeNames` stays empty until confirmed by the live reader. Package asset names are evidence for catalog identity, not proof of the name emitted by server memory.

CAP-005 — Maintainer can produce SquadReader-compatible generated metadata from reviewed mappings.

  ↳ Test: Point SquadReader at the generated data directory and verify that a known runtime vehicle, role, layer, and map resolve without changing upstream static files.

### Adapter contract

Use SquadReader's `SQREADER_DATA_DIR` override. Generated files are staged in an adapter directory, not copied over the fork's bundled vanilla data:

```text
generated/sqreader-data/
  vehicle_factions.json
  squad_pools.json
  map_config.json
  layer_bounds.json
  capzones.json
  gc_icon_manifest.json
  adapter-manifest.json
```

Mapping rules:

- `vehicle_factions.json` keys use exact runtime vehicle class names, including `_C` when emitted by the reader.
- `squad_pools.json` maps exact runtime role names; canonical kit IDs remain metadata.
- `map_config.json` and `layer_bounds.json` use exact observed layer names plus reviewed aliases.
- `capzones.json` is generated only from proven geometry. GC map points alone do not create zone shapes.
- `gc_icon_manifest.json` maps runtime and canonical identifiers to derived assets.
- Missing mappings remain `unmapped`, `ambiguous`, `unsupported`, or `unavailable`.

`adapter-manifest.json` includes source fingerprint, catalog revisions, generated files, schema versions, mapping counts, unresolved counts, and tool commit.

CAP-006 — Maintainer can build and run a minimum live GC compatibility test.

  ↳ Test: On the pinned test host, the runner completes preflight, reader health, one snapshot, a bounded watch capture, artifact validation, and report generation with a binary pass/fail result.

### Test build

The first test build is a private, single-server compatibility harness. It does not ship a public viewer.

Build prerequisites:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
```

The harness is `scripts/gc_compatibility_test.py`. It accepts:

```text
--pid <server-pid>
--data-dir <generated/sqreader-data>
--artifact-root <artifact-root>
--duration-seconds <N>
--expected-layer <exact-layer-name>
--source-manifest <source-manifest.json>
```

Execution phases:

1. Validate source, adapter, and test configuration.
2. Record server PID, executable identity, reader commit, mod revision, and data fingerprints.
3. Run `sqreader doctor` against the live process.
4. Run one `sqreader snapshot` and validate required top-level fields.
5. Run bounded `sqreader watch` with NDJSON and `.sqrx` output.
6. Parse observations into runtime inventory.
7. Validate map/layer, faction, vehicle, kit, weapon, and deployable mappings.
8. Validate generated asset manifest and required fixture assets.
9. Write JSON and Markdown reports.

Suggested private invocation:

```bash
sudo --preserve-env=SQREADER_DATA_DIR \
  .venv/bin/python scripts/gc_compatibility_test.py \
  --pid "$PID" \
  --data-dir artifacts/generated/sqreader-data \
  --artifact-root artifacts/run-<timestamp> \
  --duration-seconds 60 \
  --expected-layer "$LAYER" \
  --source-manifest artifacts/source-manifest.json
```

The harness must not enable central push, bind a public host, or write outside its artifact root.

CAP-007 — Maintainer can prove required runtime categories and asset mappings with a repeatable fixture.

  ↳ Test: A controlled run observes every required category and reports raw identifier, canonical mapping, asset reference, and confidence for each fixture.

### Fixture matrix

| Fixture | Required evidence | Failure if absent |
|---|---|---|
| Server identity | Expected process/build fingerprint | `server_mismatch` |
| Layer/map | Exact layer, map ID, image, bounds status | `layer_unresolved` |
| Faction/team | Runtime faction and canonical faction | `faction_unmapped` |
| Player/kit | Role or kit runtime name and canonical role | `kit_unmapped` |
| Weapon | Runtime weapon/class name and canonical record | `weapon_unmapped` |
| Vehicle | Runtime class, faction, kind, icon | `vehicle_unmapped` |
| Deployable | Runtime class, owner/team, icon | `deployable_unmapped` |
| Capture data | Position and proven geometry status | `geometry_unavailable` or `geometry_mismatch` |
| Recording | Valid NDJSON and `.sqrx` output | `recording_invalid` |

The first fixture may use a short controlled match, but must contain one known example from every required category. A synthetic replay can test parser/UI behavior only; it cannot prove live memory compatibility.

CAP-008 — Maintainer can diagnose extraction, reader, mapping, and asset failures independently.

  ↳ Test: Inject or reproduce one failure from each class and verify stable machine-readable error codes and actionable report output.

Required error classes:

- `source_missing`
- `source_fingerprint_changed`
- `package_index_failed`
- `asset_missing`
- `texture_decode_failed`
- `reader_attach_failed`
- `reader_offset_drift`
- `runtime_identifier_unmapped`
- `catalog_record_missing`
- `layer_alias_ambiguous`
- `metadata_coverage_unavailable`
- `asset_manifest_missing`
- `recording_invalid`

## Constraints

- Local game/mod files are the only package source.
- Server, client, and base-game packages must be pinned and fingerprinted independently.
- Raw package files and raw decoded payloads stay outside tracked source.
- Extraction is deterministic for unchanged inputs.
- Required requests fail closed; best-effort discovery cannot hide required failures.
- Reader and server run on the same Linux host with required process-memory permissions.
- First test supports one server instance and one pinned GC build.
- Test output remains private and local; central push is disabled.
- Generated metadata cannot overwrite bundled vanilla data.
- Package names, display names, and filename similarity cannot prove runtime identity.
- Map points cannot be promoted to capture-zone geometry without source evidence.
- No production integration begins until the live compatibility report passes.

## Non-goals

- Supporting all GC releases or automatic offset repair.
- Extracting and reviewing every package asset in one run.
- Shipping a public asset CDN or live match viewer.
- Reconstructing missing layer geometry or randomized objective lanes.
- Inferring runtime names from class-name conventions alone.
- Sending recordings, player data, or package content to a central service.
- Replacing GC Maps' existing map-catalog workflow.

## Success Signal

SS-1: One pinned local installation produces a complete source fingerprint, extraction report, and deterministic derived asset/catalog set with zero hidden required failures.

SS-2: One pinned live GC build passes reader health, snapshot, bounded recording, and all required fixture categories with 100% explicit mapping outcomes.

SS-3: Every approved test asset and metadata record has source provenance, canonical identity, runtime mapping status, and a reviewable failure state when unresolved.
