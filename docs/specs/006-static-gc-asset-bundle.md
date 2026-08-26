# Static GC asset bundle

Status: extraction completed from the local GC Windows client packages on 2026-08-26. Runtime asset-provider bindings are generated for the captured GC replay, and the map catalog is normalized against the GC Maps export.

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
  --artifact-root /path/to/GC-squadreader-assets/YYYY-MM-DD \
  --canonical-map-catalog /path/to/GC-config/tooling/data/map_catalog.json \
  --gc-maps-json /path/to/GC-config/tooling/data/gc.json \
  --canonical-map-assets /path/to/GC-config/web/public/maps

python scripts/verify_gc_asset_bundle.py
python scripts/verify_gc_map_coverage.py
```

The optional canonical-map arguments normalize the extractor catalog during
packaging. The canonical catalog supplies the case-stable map identity and all
25 map image pairs; the bounds export supplies exact layer coordinates and the
command's reviewed alias table handles only known legacy/server-omitted layer
IDs. The standalone normalizer remains available when the intermediate catalog
needs to be inspected before packaging:

```bash
python scripts/normalize_gc_map_catalog.py \
  --catalog /path/to/catalogs/map_catalog.json \
  --canonical-catalog /path/to/GC-config/tooling/data/map_catalog.json \
  --gc-maps-json /path/to/GC-config/tooling/data/gc.json \
  --out /path/to/catalogs/map_catalog.json
```

If `/runtime-icons/derived-manifest.json` exists beneath the artifact root,
`package_gc_assets.py` packages those outputs alongside the normal GC icon
manifest. This is used for base-game texture targets that GC blueprints point
to, such as deployable map icons and the DC-18 HUD texture.

The package command copies only JSON catalogs and decoded WebP files. It does
not copy `.pak`, `.utoc`, `.ucas`, raw texture buffers, or machine-specific
source paths. The second verifier checks the backend layer lookup and is a
release gate.

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
- 25 map images plus 25 thumbnails.
- 203 decoded icon textures, preserving the source dimensions recorded in the manifest.
- 3 icon candidates explicitly unresolved because no decodable client pixel payload was available.
- 883 exact GC role bindings, 15 vehicle bindings, 5 deployable bindings, and
  1 weapon binding in the multi-provider manifest.
- Layer bounds may be inherited only from an exact `mapId` with one authoritative bounds tuple; the audit labels this source `mapId-shared`.

## Deliberate limitations

The provider manifest covers the captured GC role catalog and the explicitly
observed live vehicle, deployable, and weapon classes. Deployable bindings
record confidence for direct property references versus reviewed UI-data or
runtime aliases. New runtime classes and marker bindings still require a fresh
snapshot plus an extraction update. The offline map catalog reports partial
World Partition coverage; static imagery and bounds are complete for the
current 188 configured layers, but the 24 reviewed aliases must be revalidated
if GC changes layer packaging.
