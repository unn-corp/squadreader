#!/usr/bin/env python3
"""Verify the committed GC-derived asset bundle without reading game files."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _repo_file(repo_root: Path, public_url: str) -> Path:
    if public_url.startswith("/icons/"):
        return repo_root / public_url.lstrip("/")
    if public_url.startswith("/maps/"):
        return repo_root / "sqmaps" / public_url.removeprefix("/maps/")
    raise ValueError(f"unsupported public asset path: {public_url}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def verify(repo_root: Path) -> list[str]:
    errors: list[str] = []
    data_root = repo_root / "data" / "static" / "gc"
    bundle_path = data_root / "asset_bundle.json"
    icon_manifest_path = data_root / "icon_manifest.json"
    map_catalog_path = data_root / "map_catalog.json"
    provider_manifest_path = repo_root / "data" / "static" / "asset_providers.json"

    for path in (bundle_path, icon_manifest_path, map_catalog_path):
        if not path.is_file():
            errors.append(f"missing manifest: {path}")
    if errors:
        return errors

    bundle = _load(bundle_path)
    icon_manifest = _load(icon_manifest_path)
    map_catalog = _load(map_catalog_path)
    provider_catalog = _load(provider_manifest_path) if provider_manifest_path.is_file() else None

    if bundle.get("schemaVersion") != 1:
        errors.append("asset bundle schemaVersion must be 1")
    if icon_manifest.get("schemaVersion") != 1:
        errors.append("icon manifest schemaVersion must be 1")
    if map_catalog.get("schemaVersion") != 4:
        errors.append("map catalog schemaVersion must be 4")
    if provider_catalog is not None:
        if provider_catalog.get("schemaVersion") != 1:
            errors.append("asset provider schemaVersion must be 1")
        providers = provider_catalog.get("providers")
        if not isinstance(providers, dict) or not providers:
            errors.append("asset provider manifest must contain providers")
        elif provider_catalog.get("defaultProviderId") not in providers:
            errors.append("asset provider defaultProviderId is not registered")

    bundled_paths: set[str] = set()
    for item in bundle.get("files", []):
        if not isinstance(item, dict):
            errors.append("bundle file entry is not an object")
            continue
        relative_path = item.get("path")
        expected_hash = item.get("sha256")
        if not isinstance(relative_path, str) or not isinstance(expected_hash, str):
            errors.append("bundle file entry lacks path/sha256")
            continue
        if not (relative_path.startswith("icons/gc/")
                or relative_path.startswith("sqmaps/gc/")
                or relative_path == "data/static/asset_providers.json"):
            errors.append(f"bundle file is outside GC asset roots: {relative_path}")
            continue
        bundled_paths.add(relative_path)
        path = repo_root / relative_path
        if not path.is_file():
            errors.append(f"missing bundled file: {relative_path}")
        elif _sha256(path) != expected_hash:
            errors.append(f"sha256 mismatch: {relative_path}")

    actual_paths = {
        str(path.relative_to(repo_root))
        for root in (repo_root / "icons" / "gc", repo_root / "sqmaps" / "gc")
        if root.is_dir()
        for path in root.glob("*.webp")
    }
    for extra in sorted(actual_paths - bundled_paths):
        errors.append(f"unlisted GC asset file: {extra}")
    for missing in sorted(bundled_paths - actual_paths):
        if missing != "data/static/asset_providers.json":
            errors.append(f"listed GC asset file is not a WebP output: {missing}")
    if provider_catalog is not None and "data/static/asset_providers.json" not in bundled_paths:
        errors.append("asset provider manifest is not listed in bundle files")

    decoded = icon_manifest.get("assets", [])
    if icon_manifest.get("decoded") != len(decoded):
        errors.append("icon decoded count does not match assets length")
    if icon_manifest.get("unresolved") != len(icon_manifest.get("failures", [])):
        errors.append("icon unresolved count does not match failures length")

    for item in decoded:
        output = item.get("output") if isinstance(item, dict) else None
        if not isinstance(output, str):
            errors.append("icon entry has no output path")
            continue
        try:
            path = _repo_file(repo_root, output)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not path.is_file():
            errors.append(f"missing icon output: {output}")
        elif path.suffix.lower() != ".webp":
            errors.append(f"icon output is not WebP: {output}")

    map_urls: set[str] = set()
    for layer_id, layer in map_catalog.get("layers", {}).items():
        if not isinstance(layer, dict):
            errors.append(f"map layer is not an object: {layer_id}")
            continue
        for key in ("imageUrl", "thumbnailUrl"):
            value = layer.get(key)
            if value is None:
                unavailable = layer.get("coverage", {}).get("unavailableCategories", [])
                categories = {
                    item.get("category")
                    for item in unavailable
                    if isinstance(item, dict)
                }
                if "imagery" not in categories:
                    errors.append(f"map layer {layer_id} has unexplained missing {key}")
                continue
            if not isinstance(value, str):
                errors.append(f"map layer {layer_id} has invalid {key}")
                continue
            if not value.startswith("/maps/gc/"):
                errors.append(f"map layer {layer_id} has unscoped {key}: {value}")
            map_urls.add(value)
    for url in map_urls:
        try:
            path = _repo_file(repo_root, url)
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not path.is_file():
            errors.append(f"missing map output: {url}")
        elif path.suffix.lower() != ".webp":
            errors.append(f"map output is not WebP: {url}")

    counts = bundle.get("counts", {})
    expected = {
        "mapLayers": len(map_catalog.get("layers", {})),
        "mapImages": len(map_urls),
        "decodedIcons": len(decoded),
        "unresolvedIcons": len(icon_manifest.get("failures", [])),
    }
    for key, value in expected.items():
        if counts.get(key) != value:
            errors.append(f"bundle count {key}={counts.get(key)!r}, expected {value}")

    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    args = parser.parse_args()
    errors = verify(args.repo_root.resolve())
    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        return 1
    print("GC asset bundle verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
