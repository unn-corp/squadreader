#!/usr/bin/env python3
"""Merge GC Maps' authoritative layer metadata into SquadReader's catalog.

The GC Maps extraction produces two useful artifacts with different jobs:

* ``map_catalog.json`` contains decoded objectives and the canonical map image
  identity; and
* ``gc.json`` contains the map/layer configuration records, including the
  runtime minimap corner coordinates.

The server package set does not contain every configured GLD package, and a
few historical layer names do not match the current ``gc.json`` raw name.
This command joins exact layer IDs first, then applies only the reviewed
aliases below. It never joins by substring or by a display-name guess.

The output remains a normal SquadReader map catalog. Added ``boundsEvidence``
fields make the provenance visible to operators without changing the reader
contract.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path
from typing import Any


# A reviewed relationship from a configured SquadReader layer to an equivalent
# source record. Values may name another layer in the input catalog or a raw
# layer in gc.json. These are intentionally complete IDs, not regex rules.
#
# The aliases cover layers whose cooked package is absent, whose historical
# name differs, or whose source record reports zero/invalid corners. They are
# still marked as reviewed-alias in the output and should be rechecked when GC
# publishes a new layer set.
REVIEWED_BOUND_ALIASES: dict[str, str] = {
    "GC_Corvette_Seed_V1": "GC_Corvette_AAS_V1",
    "GC_Geonosis_AAS_V2": "GC_Geonosis_AAS_V1",
    "GC_Geonosis_INS_V1": "GC_Geonosis_AAS_V1",
    "GC_Geonosis_INV_V2": "GC_Geonosis_INV_V1",
    "GC_Geonosis_INV_V3": "GC_Geonosis_INV_V1",
    "GC_Kashyyyk_AAS_V1": "GC_Kashyyyk_INS_V1",
    "GC_Kashyyyk_SKM_V1": "GC_Kashyyyk_INS_V1",
    "GC_Kashyyyk_SKM_V2": "GC_Kashyyyk_INS_V1",
    "GC_Kavado_INV_V2": "GC_Kavado_INV_V1",
    "GC_Kavado_RINV_V1-W": "GC_Kavado_INV_V1",
    "GC_Rhenvar_AAS_V1": "GC_Rhenvar_RAAS_V1",
    "GC_Rhenvar_AAS_V2": "GC_Rhenvar_RAAS_V1",
    "GC_Sesid_INV_V2": "GC_Sesid_INV_V1",
    "GC_Sesid_Ins_V1": "GC_Sesid_AAS_V1",
    "GC_SesidEquator_TRINV_V1": "GC_SesidEquator_RINV_V1",
    "GC_Sullust_AAS_V1": "GC_Sullust_RINV_V1",
    "GC_Sullust_INV_V1": "GC_Sullust_RINV_V1",
    "GC_Sullust_INV_V2": "GC_Sullust_RINV_V1",
    "GC_Sullust_RINV_V2-R": "GC_Sullust_RINV_V2",
    "GC_Tatooine_AAS_V1": "GC_Tatooine_RAAS_V1",
    "GC_Tatooine_INS_V1": "GC_Tatooine_SKM_V1",
    "GC_Tatooine_INV_V1": "GC_Tatooine_RINV_V1",
    "GC_Tatooine_INV_V1-R": "GC_Tatooine_RINV_V1-R",
    "GC_Tatooine_INV_V2": "GC_Tatooine_RINV_V2",
    "GC_Tatooine_RINV_V3": "GC_Tatooine_RINV_V2",
    "GC_VenatorAssault_SKM_V2": "GC_VenatorAssault_SKMSEED",
    "GC_Yavin4_AAS_V1": "GC_Yavin4_SKM_V1",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _bounds_from_gc(raw: Any) -> list[float] | None:
    if not isinstance(raw, dict):
        return None
    corners = raw.get("minimapCornersPosition")
    if not isinstance(corners, dict):
        return None
    minimum = corners.get("min")
    maximum = corners.get("max")
    if not isinstance(minimum, dict) or not isinstance(maximum, dict):
        return None
    values = [minimum.get("x"), minimum.get("y"),
              maximum.get("x"), maximum.get("y")]
    if any(isinstance(value, bool) or not isinstance(value, (int, float))
           or not math.isfinite(float(value)) for value in values):
        return None
    bounds = [float(value) for value in values]
    if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
        return None
    # (0, 0, 0, 0) is a placeholder in GC's config, not usable map geometry.
    if not any(bounds):
        return None
    return bounds


def _bounds_from_catalog(raw: Any) -> list[float] | None:
    if not isinstance(raw, dict):
        return None
    value = raw.get("worldBoundsCm")
    if not isinstance(value, list) or len(value) != 4:
        return None
    if any(isinstance(item, bool) or not isinstance(item, (int, float))
           or not math.isfinite(float(item)) for item in value):
        return None
    bounds = [float(item) for item in value]
    if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
        return None
    return bounds


def _namespaced_map_url(url: Any) -> Any:
    if not isinstance(url, str):
        return url
    if url.startswith("/maps/gc/"):
        return url
    if url.startswith("/maps/"):
        return f"/maps/gc/{url[len('/maps/'):]}"
    raise ValueError(f"unexpected canonical map URL: {url}")


def _source_record(
    layer_id: str,
    catalog_layers: dict[str, Any],
    gc_layers: dict[str, Any],
) -> tuple[list[float] | None, str | None, str | None]:
    """Return bounds, evidence method, and source layer for one layer."""
    direct = _bounds_from_catalog(catalog_layers.get(layer_id))
    if direct is not None:
        return direct, "catalog-layer", layer_id

    exact = gc_layers.get(layer_id)
    exact_bounds = _bounds_from_gc(exact)
    if exact_bounds is not None:
        return exact_bounds, "gc-json-exact", layer_id

    alias = REVIEWED_BOUND_ALIASES.get(layer_id)
    if alias is None:
        return None, None, None
    alias_bounds = _bounds_from_catalog(catalog_layers.get(alias))
    if alias_bounds is not None:
        return alias_bounds, "reviewed-alias-catalog", alias
    alias_bounds = _bounds_from_gc(gc_layers.get(alias))
    if alias_bounds is not None:
        return alias_bounds, "reviewed-alias-gc-json", alias
    raise ValueError(
        f"reviewed bounds alias has no usable source: {layer_id} -> {alias}"
    )


def normalize(
    catalog: dict[str, Any],
    canonical: dict[str, Any],
    gc_data: dict[str, Any],
    *,
    gc_data_sha256: str | None = None,
    canonical_sha256: str | None = None,
) -> dict[str, Any]:
    layers = catalog.get("layers")
    canonical_layers = canonical.get("layers")
    gc_records = gc_data.get("Maps")
    if not isinstance(layers, dict):
        raise ValueError("catalog must contain a layers object")
    if not isinstance(canonical_layers, dict):
        raise ValueError("canonical catalog must contain a layers object")
    if not isinstance(gc_records, list):
        raise ValueError("GC data must contain a Maps list")
    if set(layers) != set(canonical_layers):
        missing = sorted(set(layers) - set(canonical_layers))
        extra = sorted(set(canonical_layers) - set(layers))
        raise ValueError(
            f"layer set mismatch; missing={missing[:5]} extra={extra[:5]}"
        )

    gc_layers = {
        record["rawName"]: record
        for record in gc_records
        if isinstance(record, dict) and isinstance(record.get("rawName"), str)
    }
    output = json.loads(json.dumps(catalog))
    output_layers = output["layers"]
    evidence_counts: dict[str, int] = {}
    for layer_id, raw in output_layers.items():
        if not isinstance(raw, dict):
            raise ValueError(f"layer is not an object: {layer_id}")
        canonical_raw = canonical_layers[layer_id]
        if not isinstance(canonical_raw, dict):
            raise ValueError(f"canonical layer is not an object: {layer_id}")

        # The canonical map catalog fixes case-sensitive map identity and
        # points all variants at the same packaged image pair.
        for key in ("mapId", "mapName"):
            if key in canonical_raw:
                raw[key] = canonical_raw[key]
        if canonical_raw.get("sourceAsset") is not None:
            raw["sourceAsset"] = canonical_raw["sourceAsset"]
        for key in ("imageUrl", "thumbnailUrl"):
            if key in canonical_raw:
                raw[key] = _namespaced_map_url(canonical_raw[key])

        bounds, method, source_layer = _source_record(
            layer_id, layers, gc_layers
        )
        if bounds is not None and _bounds_from_catalog(raw) is None:
            raw["worldBoundsCm"] = bounds
            raw["boundsEvidence"] = {
                "method": method,
                "sourceLayerId": source_layer,
            }
            evidence_counts[method or "unknown"] = (
                evidence_counts.get(method or "unknown", 0) + 1
            )

    maps: dict[str, Any] = {}
    for map_id, raw in (canonical.get("maps") or {}).items():
        if isinstance(raw, dict):
            maps[map_id] = dict(raw)
    for raw in output_layers.values():
        if not isinstance(raw, dict):
            continue
        map_id = raw.get("mapId")
        if not isinstance(map_id, str) or not map_id:
            continue
        maps.setdefault(
            map_id,
            {
                "id": map_id,
                "name": raw.get("mapName"),
                "sourceAsset": raw.get("sourceAsset"),
            },
        )
    output["maps"] = dict(sorted(maps.items()))
    output["sourceEvidence"] = {
        "catalog": "GC-config/tooling/data/map_catalog.json",
        "bounds": "GC-config/tooling/data/gc.json Maps[].minimapCornersPosition",
        "exactLayerRecords": sum(
            1 for layer_id in layers
            if _bounds_from_catalog(layers[layer_id]) is None
            and _bounds_from_gc(gc_layers.get(layer_id)) is not None
        ),
        "reviewedAliasRecords": sum(
            1 for layer_id in layers
            if layer_id in REVIEWED_BOUND_ALIASES
            and _bounds_from_catalog(layers[layer_id]) is None
            and _bounds_from_gc(gc_layers.get(layer_id)) is None
        ),
        "evidenceCounts": dict(sorted(evidence_counts.items())),
        "gcDataSha256": gc_data_sha256,
        "canonicalCatalogSha256": canonical_sha256,
    }
    return output


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, required=True)
    parser.add_argument("--canonical-catalog", type=Path, required=True)
    parser.add_argument("--gc-maps-json", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()

    gc_path = args.gc_maps_json.resolve()
    canonical_path = args.canonical_catalog.resolve()
    output = normalize(
        _load(args.catalog.resolve()),
        _load(canonical_path),
        _load(gc_path),
        gc_data_sha256=_sha256(gc_path),
        canonical_sha256=_sha256(canonical_path),
    )
    args.out.resolve().parent.mkdir(parents=True, exist_ok=True)
    args.out.resolve().write_text(
        json.dumps(output, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    evidence = output["sourceEvidence"]
    print(
        f"normalized {len(output['layers'])} layers: "
        f"{evidence['exactLayerRecords']} exact GC bounds, "
        f"{evidence['reviewedAliasRecords']} reviewed aliases"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
