#!/usr/bin/env python3
"""Verify GC map/layer readiness and optionally inspect runtime recordings.

The static portion is intentionally stricter than ``verify_gc_asset_bundle``:
it verifies the backend lookup path, not just manifest hashes.  A layer is
render-ready only when its exact catalog identity has usable world bounds,
imagery, and a file that the HTTP map resolver can serve.

The runtime portion accepts one or more ``.sqrx``, JSON, or NDJSON snapshots.
It records every observed layer and runtime asset identifier, checks provider
selection, and reports exact bindings that are still missing.  It does not
pretend that an unobserved role, vehicle, deployable, or weapon has been
validated.

Examples::

    # Fail closed when any catalog layer is incomplete.
    .venv/bin/python scripts/verify_gc_map_coverage.py

    # Produce an audit report while the known extraction gaps remain.
    .venv/bin/python scripts/verify_gc_map_coverage.py --allow-incomplete \
        --json > coverage.json

    # Add live/replay evidence to the static report.
    .venv/bin/python scripts/verify_gc_map_coverage.py --allow-incomplete \
        /path/to/match.sqrx
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterator


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from sqreader.httpsrv import _resolve_sqmap  # noqa: E402
from sqreader.squad.metadata import Metadata  # noqa: E402


def _load(path: Path) -> Any:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _valid_bounds(value: Any) -> tuple[float, float, float, float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(float(v)) for v in value):
        return None
    bounds = tuple(float(v) for v in value)
    if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
        return None
    return bounds


def _asset_file(repo_root: Path, url: Any) -> Path | None:
    """Resolve one namespaced map URL, rejecting traversal and subdirectories."""
    prefix = "/maps/gc/"
    if not isinstance(url, str) or not url.startswith(prefix):
        return None
    relative = url[len(prefix):]
    candidate = Path(relative)
    if (not relative or candidate.name != relative
            or candidate.suffix.lower() != ".webp"
            or any(part in ("", ".", "..") for part in candidate.parts)):
        return None
    root = (repo_root / "sqmaps" / "gc").resolve()
    path = (root / candidate).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        return None
    return path


def _map_bounds_index(layers: dict[str, Any]) -> dict[str, set[tuple[float, ...]]]:
    by_map: dict[str, set[tuple[float, ...]]] = defaultdict(set)
    for raw in layers.values():
        if not isinstance(raw, dict):
            continue
        map_id = raw.get("mapId")
        bounds = _valid_bounds(raw.get("worldBoundsCm"))
        if isinstance(map_id, str) and bounds is not None:
            by_map[map_id].add(bounds)
    return by_map


def _normalise_layer_key(value: str) -> str:
    return "".join(ch.lower() for ch in value if ch.isalnum())


def _catalog_layer_aliases(repo_root: Path) -> dict[str, set[str]]:
    path = repo_root / "data" / "static" / "gc" / "map_catalog.json"
    if not path.is_file():
        return {}
    catalog = _load(path)
    layers = catalog.get("layers") if isinstance(catalog, dict) else None
    if not isinstance(layers, dict):
        return {}
    aliases: dict[str, set[str]] = defaultdict(set)
    for layer_id, raw in layers.items():
        if not isinstance(layer_id, str) or not isinstance(raw, dict):
            continue
        for value in (
            layer_id,
            layer_id.removeprefix("GC_"),
            raw.get("displayName"),
            raw.get("layerId"),
            raw.get("mapName"),
        ):
            if isinstance(value, str) and value:
                aliases[_normalise_layer_key(value)].add(layer_id)
    return aliases


def _resolved_bounds(
    raw: dict[str, Any],
    by_map: dict[str, set[tuple[float, ...]]],
) -> tuple[tuple[float, ...] | None, str | None]:
    direct = _valid_bounds(raw.get("worldBoundsCm"))
    if direct is not None:
        return direct, "layer"
    map_id = raw.get("mapId")
    candidates = by_map.get(map_id, set()) if isinstance(map_id, str) else set()
    if len(candidates) == 1:
        return next(iter(candidates)), "mapId-shared"
    if len(candidates) > 1:
        return None, "ambiguous-mapId"
    return None, None


def verify_static(repo_root: Path) -> dict[str, Any]:
    """Return a deterministic static readiness report for the packaged bundle."""
    data_root = repo_root / "data" / "static"
    catalog_path = data_root / "gc" / "map_catalog.json"
    if not catalog_path.is_file():
        return {
            "ok": False,
            "error": f"missing catalog: {catalog_path}",
            "layers": [],
            "summary": {},
        }

    catalog = _load(catalog_path)
    layers = catalog.get("layers") if isinstance(catalog, dict) else None
    if not isinstance(layers, dict):
        return {
            "ok": False,
            "error": "GC map catalog must contain a layers object",
            "layers": [],
            "summary": {},
        }

    by_map = _map_bounds_index(layers)
    metadata = Metadata.load(data_root)
    sqmaps_dir = repo_root / "sqmaps"
    layer_reports: list[dict[str, Any]] = []
    issues_by_category: Counter[str] = Counter()
    map_groups: dict[str, dict[str, Any]] = {}

    for layer_id, raw in sorted(layers.items()):
        issues: list[str] = []
        if not isinstance(raw, dict):
            layer_reports.append({"layerId": layer_id, "issues": ["invalid_record"]})
            issues_by_category["invalid_record"] += 1
            continue

        bounds, bounds_source = _resolved_bounds(raw, by_map)
        if bounds is None:
            issues.append("ambiguous_bounds" if bounds_source == "ambiguous-mapId"
                          else "missing_bounds")

        image_path = _asset_file(repo_root, raw.get("imageUrl"))
        if image_path is None:
            issues.append("missing_image" if raw.get("imageUrl") is None
                          else "invalid_image_url")
        elif not image_path.is_file():
            issues.append("missing_image_file")

        thumbnail_path = _asset_file(repo_root, raw.get("thumbnailUrl"))
        if thumbnail_path is None:
            issues.append("missing_thumbnail" if raw.get("thumbnailUrl") is None
                          else "invalid_thumbnail_url")
        elif not thumbnail_path.is_file():
            issues.append("missing_thumbnail_file")

        backend_record = metadata.layer_bounds_for(layer_id)
        if backend_record is None:
            issues.append("backend_unresolved")
            texture_path = None
        else:
            expected_texture = image_path.stem if image_path is not None else None
            if expected_texture and backend_record.get("texture") != expected_texture:
                issues.append("backend_texture_mismatch")
            if bounds is not None:
                actual = (
                    backend_record.get("topLeft", {}).get("x"),
                    backend_record.get("topLeft", {}).get("y"),
                    backend_record.get("bottomRight", {}).get("x"),
                    backend_record.get("bottomRight", {}).get("y"),
                )
                if tuple(float(v) for v in actual) != bounds:
                    issues.append("backend_bounds_mismatch")
            texture_path = _resolve_sqmap(
                sqmaps_dir, str(backend_record.get("texture") or ""))
            if texture_path is None:
                issues.append("texture_file_missing")

        for issue in issues:
            issues_by_category[issue] += 1

        map_id = raw.get("mapId")
        group_key = map_id if isinstance(map_id, str) and map_id else f"layer:{layer_id}"
        group = map_groups.setdefault(
            group_key,
            {"mapId": map_id, "mapNames": set(), "layers": 0,
             "renderReady": 0, "issues": Counter()},
        )
        if isinstance(raw.get("mapName"), str):
            group["mapNames"].add(raw["mapName"])
        group["layers"] += 1
        if not issues:
            group["renderReady"] += 1
        for issue in issues:
            group["issues"][issue] += 1

        layer_reports.append({
            "layerId": layer_id,
            "mapId": map_id,
            "mapName": raw.get("mapName"),
            "boundsSource": bounds_source,
            "backendBoundsSource": (backend_record or {}).get("boundsSource"),
            "imageUrl": raw.get("imageUrl"),
            "thumbnailUrl": raw.get("thumbnailUrl"),
            "backendResolved": backend_record is not None,
            "textureFile": str(texture_path) if texture_path else None,
            "issues": issues,
        })

    render_ready = sum(not item.get("issues") for item in layer_reports)
    summary = {
        "catalogLayers": len(layer_reports),
        "renderReadyLayers": render_ready,
        "incompleteLayers": len(layer_reports) - render_ready,
        "metadataResolvedLayers": sum(item["backendResolved"] for item in layer_reports),
        "mapIds": len(map_groups),
        "issueCounts": dict(sorted(issues_by_category.items())),
        "boundsSources": dict(sorted(Counter(
            item["boundsSource"] for item in layer_reports
            if item.get("boundsSource")
        ).items())),
    }
    groups = []
    for group in sorted(map_groups.values(), key=lambda item: str(item["mapId"])):
        groups.append({
            "mapId": group["mapId"],
            "mapNames": sorted(group["mapNames"]),
            "layers": group["layers"],
            "renderReady": group["renderReady"],
            "issueCounts": dict(sorted(group["issues"].items())),
        })

    return {
        "ok": not issues_by_category,
        "summary": summary,
        "mapGroups": groups,
        "layers": layer_reports,
    }


def _iter_json_records(path: Path) -> Iterator[dict[str, Any]]:
    if path.suffix.lower() == ".sqrx":
        from sqreader.sqrx import SqrxReader

        with SqrxReader(path) as reader:
            for line in reader.lines():
                value = json.loads(line)
                if isinstance(value, dict):
                    yield value
        return

    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        value = json.loads(text)
        if isinstance(value, dict) and isinstance(value.get("frames"), list):
            for frame in value["frames"]:
                if isinstance(frame, dict):
                    yield frame
        elif isinstance(value, dict):
            yield value
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    yield item
        return

    for _line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        if isinstance(value, dict):
            yield value


def _add_observed(
    observed: dict[str, set[str]],
    unbound: dict[str, set[str]],
    category: str,
    value: Any,
    bindings: dict[str, Any],
) -> None:
    if not isinstance(value, str) or not value:
        return
    observed[category].add(value)
    if value not in bindings:
        unbound[category].add(value)


def verify_runtime(repo_root: Path, snapshot_paths: list[Path]) -> dict[str, Any]:
    """Check observed replay layers, provider choice, and exact asset bindings."""
    metadata = Metadata.load(repo_root / "data" / "static")
    providers = metadata.asset_providers().get("providers", {})
    observed: dict[str, set[str]] = defaultdict(set)
    unbound: dict[str, set[str]] = defaultdict(set)
    layer_observations: dict[str, dict[str, Any]] = {}
    observed_catalog_layers: set[str] = set()
    ambiguous_observed_layers: set[str] = set()
    catalog_aliases = _catalog_layer_aliases(repo_root)
    provider_observations: Counter[str] = Counter()
    errors: list[str] = []
    frames = 0

    for snapshot_path in snapshot_paths:
        try:
            records = _iter_json_records(snapshot_path)
            for snap in records:
                frames += 1
                raw_game_state = snap.get("gameState")
                # .sqrx position frames intentionally omit full game state;
                # identity belongs to the preceding FULL frame and is not a
                # new map/provider observation.
                if snap.get("t") == "pos" and not raw_game_state:
                    continue
                game_state = raw_game_state or {}
                teams = snap.get("teams") or []
                players = snap.get("players") or []
                vehicles = snap.get("vehicles") or []
                if not isinstance(game_state, dict):
                    errors.append(f"{snapshot_path}: gameState is not an object")
                    continue
                expected_provider_id = metadata.asset_provider_id(
                    game_state,
                    teams if isinstance(teams, list) else [],
                    players if isinstance(players, list) else [],
                    vehicles if isinstance(vehicles, list) else [],
                )
                expected_provider = (providers.get(expected_provider_id, {})
                                     if isinstance(providers, dict) else {})
                if not isinstance(expected_provider, dict):
                    expected_provider = {}
                provider_observations[expected_provider_id or "<none>"] += 1
                emitted_provider = game_state.get("assetProviderId")
                if (isinstance(emitted_provider, str)
                        and emitted_provider != expected_provider_id):
                    errors.append(
                        f"{snapshot_path}: provider mismatch: emitted "
                        f"{emitted_provider!r}, expected {expected_provider_id!r}"
                    )

                layer_name = game_state.get("mapName")
                layer_payload = game_state.get("layer")
                if not isinstance(layer_name, str) or not layer_name:
                    errors.append(f"{snapshot_path}: frame has no gameState.mapName")
                else:
                    catalog_matches = catalog_aliases.get(_normalise_layer_key(layer_name), set())
                    if len(catalog_matches) == 1:
                        observed_catalog_layers.update(catalog_matches)
                    elif len(catalog_matches) > 1:
                        ambiguous_observed_layers.add(layer_name)
                    item = layer_observations.setdefault(
                        layer_name,
                        {"frames": 0, "metadataResolved": False,
                         "layerPayloadPresent": False, "issues": set()},
                    )
                    item["frames"] += 1
                    record = metadata.layer_bounds_for(layer_name)
                    item["metadataResolved"] = record is not None
                    if record is None:
                        item["issues"].add("backend_unresolved")
                    else:
                        item["layerPayloadPresent"] |= isinstance(layer_payload, dict)
                        if not isinstance(layer_payload, dict):
                            item["issues"].add("missing_layer_payload")
                        texture = record.get("texture")
                        if _resolve_sqmap(repo_root / "sqmaps", str(texture or "")) is None:
                            item["issues"].add("texture_file_missing")

                role_bindings = expected_provider.get("roleIcons") or {}
                vehicle_bindings = expected_provider.get("vehicleIcons") or {}
                deployable_bindings = expected_provider.get("deployableIcons") or {}
                marker_bindings = expected_provider.get("markerIcons") or {}
                weapon_bindings = expected_provider.get("weaponIcons") or {}
                for player in players if isinstance(players, list) else []:
                    if not isinstance(player, dict):
                        continue
                    _add_observed(observed, unbound, "roles", player.get("roleId"), role_bindings)
                    soldier = player.get("soldier") or {}
                    if isinstance(soldier, dict):
                        weapon = soldier.get("weapon") or {}
                        if isinstance(weapon, dict):
                            _add_observed(
                                observed, unbound, "weapons", weapon.get("className"),
                                weapon_bindings,
                            )
                for vehicle in vehicles if isinstance(vehicles, list) else []:
                    if isinstance(vehicle, dict):
                        _add_observed(
                            observed, unbound, "vehicles", vehicle.get("classShort"),
                            vehicle_bindings,
                        )
                for deployable in snap.get("deployables") or []:
                    if isinstance(deployable, dict):
                        _add_observed(
                            observed, unbound, "deployables", deployable.get("classShort"),
                            deployable_bindings,
                        )
                for marker in snap.get("markers") or []:
                    if isinstance(marker, dict):
                        _add_observed(
                            observed, unbound, "markers", marker.get("classShort"),
                            marker_bindings,
                        )
        except Exception as exc:
            errors.append(f"{snapshot_path}: {type(exc).__name__}: {exc}")

    layer_list = []
    for name, item in sorted(layer_observations.items()):
        layer_list.append({
            "name": name,
            "frames": item["frames"],
            "metadataResolved": item["metadataResolved"],
            "layerPayloadPresent": item["layerPayloadPresent"],
            "issues": sorted(item["issues"]),
        })

    expected_catalog_layers = sorted({
        layer_id for layer_ids in catalog_aliases.values() for layer_id in layer_ids
    })
    unobserved_catalog_layers = sorted(
        set(expected_catalog_layers) - observed_catalog_layers
    )
    if ambiguous_observed_layers:
        errors.extend(
            f"ambiguous runtime layer alias: {name}"
            for name in sorted(ambiguous_observed_layers)
        )

    return {
        "ok": (
            not errors
            and not unobserved_catalog_layers
            and all(not item["issues"] for item in layer_observations.values())
        ),
        "frames": frames,
        "layers": layer_list,
        "expectedCatalogLayers": len(expected_catalog_layers),
        "observedCatalogLayers": len(observed_catalog_layers),
        "unobservedCatalogLayers": unobserved_catalog_layers,
        "providerObservations": dict(sorted(provider_observations.items())),
        "observed": {key: sorted(values) for key, values in sorted(observed.items())},
        "unbound": {key: sorted(values) for key, values in sorted(unbound.items())},
        "errors": errors,
    }


def _print_human(report: dict[str, Any]) -> None:
    static = report["static"]
    summary = static.get("summary", {})
    status = "PASS" if static.get("ok") else "INCOMPLETE"
    print(
        f"GC map coverage: {status}\n"
        f"  layers: {summary.get('renderReadyLayers', 0)}/"
        f"{summary.get('catalogLayers', 0)} render-ready\n"
        f"  backend metadata: {summary.get('metadataResolvedLayers', 0)}/"
        f"{summary.get('catalogLayers', 0)} resolved"
    )
    for category, count in (summary.get("issueCounts") or {}).items():
        print(f"  {category}: {count}")

    runtime = report.get("runtime")
    if runtime is not None:
        print(f"Runtime coverage: {'PASS' if runtime['ok'] else 'INCOMPLETE'}")
        print(
            f"  frames: {runtime['frames']}; catalog layers observed: "
            f"{runtime['observedCatalogLayers']}/{runtime['expectedCatalogLayers']}"
        )
        for provider, count in runtime.get("providerObservations", {}).items():
            print(f"  provider {provider}: {count} frame(s)")
        for category, values in runtime.get("unbound", {}).items():
            print(f"  unbound {category}: {len(values)}")
        if runtime.get("unobservedCatalogLayers"):
            print(f"  unobserved catalog layers: {len(runtime['unobservedCatalogLayers'])}")
        for error in runtime.get("errors", []):
            print(f"  ERROR: {error}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("snapshots", nargs="*", type=Path)
    parser.add_argument(
        "--repo-root", type=Path, default=REPO_ROOT,
        help="SquadReader checkout containing data/static and sqmaps",
    )
    parser.add_argument("--json", action="store_true", help="emit the full JSON report")
    parser.add_argument(
        "--allow-incomplete", action="store_true",
        help="report known gaps but return success",
    )
    args = parser.parse_args()
    repo_root = args.repo_root.resolve()
    report: dict[str, Any] = {"static": verify_static(repo_root)}
    if args.snapshots:
        report["runtime"] = verify_runtime(repo_root, [p.resolve() for p in args.snapshots])

    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_human(report)
    ok = report["static"].get("ok", False)
    if report.get("runtime") is not None:
        ok = ok and report["runtime"].get("ok", False)
    return 0 if ok or args.allow_incomplete else 1


if __name__ == "__main__":
    raise SystemExit(main())
