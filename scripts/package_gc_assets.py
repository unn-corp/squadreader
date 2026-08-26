#!/usr/bin/env python3
"""Package a validated GC Maps extraction as derived, reviewable assets.

The extraction itself stays in GC-config/tooling, where the shared ue_zen reader
and its fail-closed policies live. This script only packages the resulting
catalogs and decoded WebP files into the SquadReader fork. Raw UE containers,
temporary exports, and machine-specific absolute paths are never copied.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any


CATALOG_NAMES = (
    "faction_names",
    "roles",
    "layer_setups",
    "vehicle_counts",
    "vehicle_profiles",
    "vehicle_delays",
)


def _load_json(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as handle:
            temporary_path = Path(handle.name)
            json.dump(value, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary_path, path)
        temporary_path = None
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)


def _copy(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _map_url(url: str) -> str:
    prefix = "/maps/"
    if not url.startswith(prefix):
        raise ValueError(f"unexpected map URL: {url}")
    return f"/maps/gc/{url[len(prefix):]}"


def _package_map_catalog(source: Path, destination: Path) -> tuple[dict[str, Any], set[str]]:
    catalog = _load_json(source)
    if not isinstance(catalog, dict) or not isinstance(catalog.get("layers"), dict):
        raise ValueError("map catalog must contain a layers object")

    map_files: set[str] = set()
    for layer in catalog["layers"].values():
        if not isinstance(layer, dict):
            raise ValueError("map catalog layer is not an object")
        for key in ("imageUrl", "thumbnailUrl"):
            value = layer.get(key)
            if value is None:
                continue
            if not isinstance(value, str):
                raise ValueError(f"map catalog {key} is not a string")
            layer[key] = _map_url(value)
            map_files.add(Path(value).name)

    _write_json(destination, catalog)
    return catalog, map_files


def _package_icon_manifest(
    source: Path,
    destination: Path,
    derived_dir: Path,
    repo_root: Path,
) -> tuple[dict[str, Any], int]:
    raw = _load_json(source)
    if not isinstance(raw, dict) or not isinstance(raw.get("assets"), list):
        raise ValueError("icon manifest must contain an assets list")

    assets: list[dict[str, Any]] = []
    for item in raw["assets"]:
        if not isinstance(item, dict):
            raise ValueError("icon manifest asset is not an object")
        source_asset = item.get("asset")
        output = item.get("output")
        if not isinstance(source_asset, str) or not isinstance(output, str):
            raise ValueError("icon manifest asset lacks asset/output")
        filename = Path(output).name
        source_file = derived_dir / filename
        if not source_file.is_file():
            raise FileNotFoundError(source_file)
        _copy(source_file, repo_root / "icons" / "gc" / filename)
        assets.append(
            {
                "assetPath": source_asset,
                "output": f"/icons/gc/{filename}",
                "width": item.get("width"),
                "height": item.get("height"),
                "channelOrder": item.get("channelOrder"),
                "format": item.get("format"),
                "status": "decoded",
            }
        )

    failures: list[dict[str, Any]] = []
    for item in raw.get("failures", []):
        if not isinstance(item, dict):
            raise ValueError("icon manifest failure is not an object")
        failures.append(
            {
                "assetPath": item.get("Asset"),
                "output": None,
                "status": "unavailable",
                "error": item.get("Error", "unknown extraction failure"),
            }
        )

    packaged = {
        "schemaVersion": 1,
        "source": raw.get("source", "local GC client packages"),
        "decoded": len(assets),
        "unresolved": len(failures),
        "assets": assets,
        "failures": failures,
    }
    _write_json(destination, packaged)
    return packaged, len(assets)


def package(artifact_root: Path, repo_root: Path) -> None:
    catalogs_root = artifact_root / "catalogs"
    icon_manifest_source = artifact_root / "icons" / "derived-manifest.json"
    icon_derived_root = artifact_root / "icons" / "derived"
    map_catalog_source = catalogs_root / "map_catalog.json"

    gc_data = repo_root / "data" / "static" / "gc"
    gc_maps = repo_root / "sqmaps" / "gc"
    gc_data.mkdir(parents=True, exist_ok=True)
    gc_maps.mkdir(parents=True, exist_ok=True)

    for name in CATALOG_NAMES:
        _copy(catalogs_root / f"{name}.json", gc_data / f"{name}.json")

    map_catalog, map_files = _package_map_catalog(
        map_catalog_source,
        gc_data / "map_catalog.json",
    )
    for filename in sorted(map_files):
        _copy(artifact_root / "maps" / filename, gc_maps / filename)

    icon_manifest, icon_count = _package_icon_manifest(
        icon_manifest_source,
        gc_data / "icon_manifest.json",
        icon_derived_root,
        repo_root,
    )

    icon_files = [
        repo_root / "icons" / "gc" / Path(item["output"]).name
        for item in icon_manifest["assets"]
    ]
    map_files_in_repo = [repo_root / "sqmaps" / "gc" / filename for filename in map_files]
    packaged_files = [*icon_files, *map_files_in_repo]
    files = [
        {
            "path": str(path.relative_to(repo_root)),
            "sha256": _sha256(path),
        }
        for path in sorted(packaged_files)
    ]

    artifact_date = artifact_root.name
    bundle = {
        "schemaVersion": 1,
        "bundle": "gc-static-assets",
        "generatedDate": artifact_date,
        "source": {
            "workshopId": "2428425228",
            "modPakFlavor": "Windows client",
            "gamePakSource": "local Steam installation",
            "extractionTooling": "unn-corp/gc-maps tooling",
            "rawPackagesCommitted": False,
            "sourceFingerprint": map_catalog.get("sourceFingerprint"),
        },
        "counts": {
            "factions": len(_load_json(gc_data / "faction_names.json")),
            "roles": _load_json(gc_data / "roles.json").get("role_count"),
            "layerSetups": len(_load_json(gc_data / "layer_setups.json")),
            "vehicleCountSetups": len(_load_json(gc_data / "vehicle_counts.json")),
            "vehicleDelaySetups": len(_load_json(gc_data / "vehicle_delays.json")),
            "mapLayers": len(map_catalog["layers"]),
            "mapImages": len(map_files),
            "decodedIcons": icon_count,
            "unresolvedIcons": len(icon_manifest["failures"]),
        },
        "manifests": {
            "dataRoot": "data/static/gc",
            "iconManifest": "data/static/gc/icon_manifest.json",
            "mapCatalog": "data/static/gc/map_catalog.json",
            "mapAssetRoot": "sqmaps/gc",
            "iconAssetRoot": "icons/gc",
        },
        "files": files,
        "limitations": [
            (
                "Runtime class-name bindings are intentionally absent until a live GC "
                "server snapshot is captured."
            ),
            (
                "Three discovered icon candidates were not decodable UTexture2D client "
                "payloads and remain explicitly unresolved."
            ),
            "World Partition actor coverage is partial in the offline map catalog.",
        ],
    }
    _write_json(gc_data / "asset_bundle.json", bundle)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--artifact-root", type=Path, required=True)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    package(args.artifact_root.resolve(), args.repo_root.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
