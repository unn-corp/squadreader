# GC Runtime Inventory and Metadata Adapter

**Status:** Draft  
**Version:** 0.1  
**Date:** 2026-08-25  

## Purpose

Create a repeatable bridge between GC Maps source data and SquadReader runtime observations. Keep raw observations, canonical GC records, and SquadReader-compatible metadata separate.

## Source inputs

| Input | Use | Required state |
|---|---|---|
| GC layer catalog | Map IDs, layer IDs, images, points, bounds, coverage | Existing catalog or explicit unavailable state |
| GC faction catalog | Faction IDs, vehicle references, display names | Existing catalog with stable canonical IDs |
| GC role catalog | Kits, roles, pools, faction relationships | Existing catalog with stable canonical IDs |
| GC vehicle catalog | Vehicle display names, factions, variants | Existing catalog; disputed records remain flagged |
| GC package assets | Textures and icons | Local extraction input; never raw-committed |
| Live SquadReader observation | Exact runtime class and object identifiers | Captured from pinned GC server build |

## Identity model

Each runtime observation must preserve both identifiers:

```json
{
  "category": "vehicle",
  "runtimeName": "<exact observed value>",
  "canonicalId": "GAR_LAAT",
  "status": "mapped",
  "displayName": "LAAT Gunship",
  "source": {
    "serverBuild": "<pinned build>",
    "modBuild": "<pinned build>",
    "catalogVersion": "<catalog revision>"
  }
}
```

Allowed `status` values:

- `mapped` — one verified canonical match.
- `unmapped` — runtime value observed; no catalog match.
- `ambiguous` — multiple plausible catalog matches.
- `unsupported` — reader observed category but cannot expose required value.
- `unavailable` — source artifact does not contain required data.

No adapter may derive a canonical ID from display-name similarity alone.

## Generated outputs

### 1. Runtime inventory

`gc_runtime_inventory.json`

Contains every observed raw identifier, category, occurrence count, sample context, source build, and mapping status. This is the primary reverse-engineering artifact.

### 2. Canonical mapping manifest

`gc_runtime_manifest.json`

Maps verified runtime names to GC Maps IDs. Includes aliases, faction, category, display name, confidence, provenance, and unresolved values.

### 3. SquadReader metadata adapter

Generate or populate the metadata consumed by SquadReader:

- `vehicle_factions.json`
- `squad_pools.json`
- `map_config.json`
- `layer_bounds.json`
- `capzones.json` where geometry is proven
- `gc_icon_manifest.json`

GC-specific metadata must remain namespaced or clearly marked so future upstream Squad updates do not overwrite it.

### 4. Asset manifest

`gc_asset_manifest.json`

Each asset record contains:

- canonical ID
- category
- source package and asset path
- output path
- dimensions and format
- extraction status
- provenance hash
- fallback asset, if any

## Layer handling

Layer resolution uses the exact observed layer name first. A verified alias table may resolve known naming differences. Fuzzy matching may suggest candidates for review but must not silently select a map.

Coverage must be recorded independently for:

- imagery
- world bounds
- points
- capture-zone geometry
- active-layout behavior

Map points are not equivalent to capture-zone geometry. Missing geometry stays missing.

## Mapping workflow

1. Pin server, mod, client-asset, and catalog revisions.
2. Capture live runtime inventory.
3. Normalize observations without removing raw names.
4. Match against GC canonical catalogs.
5. Review every unmapped and ambiguous value.
6. Generate SquadReader metadata and asset manifests.
7. Validate against recorded fixtures.
8. Commit only derived manifests and approved assets.

## Acceptance checks

- Every fixture observation has a raw identifier.
- Every mapped identifier has a source record and provenance.
- No duplicate canonical IDs exist within one category without an explicit variant rule.
- No missing value is converted to a guessed default.
- Re-running extraction is deterministic for unchanged inputs.
- Catalog diffs identify removals and renames before deployment.
