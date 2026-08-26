# Static GC asset bundle

Status: extraction completed from the local GC Windows client packages on 2026-08-26. Runtime asset-provider bindings are now generated for the captured GC replay; additional live classes remain incremental.

## Purpose

Package only reviewed, derived GC assets and metadata into the SquadReader fork. The raw Unreal containers stay on the extraction host and are never committed.

The extraction uses the shared GC Maps tooling patterns:

- `ue_zen.py` is the structured package reader.
- Tagged properties are serialized with explicit failure states.
- Exact package/layer identity is preferred over fuzzy matching.
- Partial and unavailable coverage is preserved rather than filled with guesses.
- Derived artifacts are namespaced under `gc/` and independently verified.

## Reproduction

Run the GC Maps extractors against a local Steam installation, then package the generated artifact root:

```bash
python scripts/package_gc_assets.py \
  --artifact-root /path/to/GC-squadreader-assets/YYYY-MM-DD

python scripts/verify_gc_asset_bundle.py
```

The package command copies only JSON catalogs and decoded WebP files. It does not copy `.pak`, `.utoc`, `.ucas`, raw texture buffers, or machine-specific source paths.

## Committed layout

```text
data/static/gc/
  asset_bundle.json
  faction_names.json
  icon_manifest.json
  layer_setups.json
  map_catalog.json
  roles.json
  vehicle_counts.json
  vehicle_delays.json
  vehicle_profiles.json
data/static/
  asset_providers.json
icons/gc/
sqmaps/gc/
```

The icon and map manifests use public paths rooted at `/icons/gc/` and `/maps/gc/`, so the bundle cannot shadow existing vanilla Squad assets.

## Current extraction

- 42 faction names.
- 1,640 roles, including 376 squad-leader kits.
- 156 layer setup records.
- 687 vehicle count setups and 687 vehicle delay setups.
- 188 configured map layers.
- 23 map images plus 23 thumbnails.
- 199 decoded icon textures, preserving the source dimensions recorded in the manifest.
- 3 icon candidates explicitly unresolved because no decodable client pixel payload was available.
- 883 exact GC role bindings and 14 exact GC vehicle bindings in the multi-provider manifest.

## Deliberate limitations

The provider manifest covers the captured GC role catalog and the explicitly observed live vehicle classes. New runtime classes, weapons, deployables, and marker bindings still require a fresh snapshot plus an extraction update. The offline map catalog also reports partial World Partition coverage and leaves layers without safe imagery as `null` rather than borrowing an unverified image.
