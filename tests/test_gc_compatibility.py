"""Regression coverage for GC's Blueprint-derived runtime classes."""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, "scripts")

import verify_gc_map_coverage as coverage
from normalize_gc_map_catalog import normalize
from extract_asset_provider import VEHICLE_ICON_ASSETS, _runtime_bindings

from sqreader.squad import snapshot as sn
from sqreader.squad.metadata import Metadata
from sqreader.httpsrv import _resolve_sqmap


class _ClassChainPM:
    def __init__(self, supers: dict[int, int]) -> None:
        self._supers = supers

    def read_u64(self, addr: int) -> int:
        # USTRUCT_SUPER_STRUCT is 0x40.  Returning zero terminates the chain
        # just like the root UObject class does in the live process.
        if addr % 0x1000 == 0x40:
            return self._supers.get(addr - 0x40, 0)
        raise OSError(f"unexpected read at 0x{addr:x}")


def test_gc_player_state_blueprint_subclass_matches_sq_player_state():
    sq_player_state = 0x1000
    gc_player_state = 0x2000
    pm = _ClassChainPM({gc_player_state: sq_player_state, sq_player_state: 0})
    caches = sn.SnapshotCaches()

    assert sn._matches_player_state_class(
        pm,
        gc_player_state,
        sq_player_state,
        caches.is_player_state,
        caches.subclass_gen,
    )


def test_gc_map_catalog_is_auto_detected_from_runtime_display_name(tmp_path):
    gc_dir = tmp_path / "gc"
    gc_dir.mkdir()
    (gc_dir / "map_catalog.json").write_text(json.dumps({
        "layers": {
            "GC_BespinPlatforms_AAS_V2": {
                "mapId": "gc-bespin",
                "mapName": "BespinPlatforms",
                "displayName": "GC_BespinPlatforms_AAS_V2",
                "worldBoundsCm": [-203192, -203192, 203192, 203192],
                "imageUrl": "/maps/gc/267f397274370fc9.webp",
            },
        },
    }), encoding="utf-8")

    metadata = Metadata.load(tmp_path)
    layer = metadata.layer_bounds_for("Bespin Platforms AAS V2")

    assert layer is not None
    assert layer["texture"] == "267f397274370fc9"
    assert layer["topLeft"] == {"x": -203192.0, "y": -203192.0}
    assert layer["bottomRight"] == {"x": 203192.0, "y": 203192.0}


def test_gc_map_catalog_normalizer_uses_exact_gc_bounds_and_namespaced_images():
    catalog = {
        "schemaVersion": 4,
        "sourceFingerprint": "pak-fingerprint",
        "layers": {
            "GC_Test_AAS_V1": {
                "layerId": "GC_Test_AAS_V1",
                "mapId": "old-case-id",
                "mapName": "test",
                "imageUrl": "/maps/old-case-id.webp",
                "thumbnailUrl": "/maps/old-case-id.thumb.webp",
                "worldBoundsCm": None,
            },
        },
        "maps": {},
    }
    canonical = {
        "layers": {
            "GC_Test_AAS_V1": {
                "mapId": "canonical-id",
                "mapName": "Test",
                "imageUrl": "/maps/canonical-id.webp",
                "thumbnailUrl": "/maps/canonical-id.thumb.webp",
                "sourceAsset": "/ANE_BASE/Maps/Test/GLD/GC_Test_AAS_V1",
            },
        },
        "maps": {
            "canonical-id": {
                "id": "canonical-id",
                "name": "Test",
                "sourceAsset": "/ANE_BASE/Maps/Test/GLD/GC_Test_AAS_V1",
            },
        },
    }
    gc_data = {
        "Maps": [{
            "rawName": "GC_Test_AAS_V1",
            "minimapCornersPosition": {
                "min": {"x": -10, "y": -20},
                "max": {"x": 30, "y": 40},
            },
        }],
    }

    output = normalize(catalog, canonical, gc_data)
    layer = output["layers"]["GC_Test_AAS_V1"]

    assert layer["mapId"] == "canonical-id"
    assert layer["imageUrl"] == "/maps/gc/canonical-id.webp"
    assert layer["thumbnailUrl"] == "/maps/gc/canonical-id.thumb.webp"
    assert layer["worldBoundsCm"] == [-10.0, -20.0, 30.0, 40.0]
    assert layer["boundsEvidence"] == {
        "method": "gc-json-exact",
        "sourceLayerId": "GC_Test_AAS_V1",
    }


def test_packaged_gc_map_catalog_is_strictly_render_ready():
    report = coverage.verify_static(Path(__file__).resolve().parents[1])

    assert report["ok"], report["summary"]
    assert report["summary"]["catalogLayers"] == 188
    assert report["summary"]["renderReadyLayers"] == 188


def test_gc_runtime_asset_bindings_require_available_exact_texture_targets():
    index = {
        **{asset: (None, 0) for asset in VEHICLE_ICON_ASSETS.values()},
        "/Game/UI/HUD/DeployableIcons/deployable_AntiAirGun": (None, 0),
        "/ANE_BASE/Art/Icons/Misc/ammocrate": (None, 0),
        "/ANE_BASE/Gameplay/GameModes/Contention/ShieldIcon": (None, 0),
        "/Game/UI/HUD/DeployableIcons/deployable_helipad": (None, 0),
        "/Game/UI/HUD/DeployableIcons/deployable_repairstation": (None, 0),
        "/ANE_BASE/UI/HUD/Inventory/Weapons/Rifles/DC-17_Pistol_Hud": (None, 0),
    }

    bindings, sources, unresolved = _runtime_bindings(index)

    assert not unresolved
    assert "BP_Emplaced_ZU23-2_Laser_Antiaircannon_Base_C" in bindings["vehicleIcons"]
    assert len(bindings["deployableIcons"]) == 5
    assert bindings["weaponIcons"]["BP_DC-18_C"].endswith("1a95223542eb1604.webp")
    assert sources["weaponIcons"]["BP_DC-18_C"].endswith("DC-17_Pistol_Hud")


def test_asset_provider_autodetects_gc_game_state_from_loaded_catalog():
    metadata = Metadata.load(Path(__file__).resolve().parents[1] / "data" / "static")

    assert metadata.asset_provider_id(
        {"instanceClass": "BP_GameStateGC_C"},
        [{"factionId": "GARP1_CombinedArms"}],
        [],
        [],
    ) == "gc"


def test_gc_map_texture_resolves_from_packaged_subdirectory(tmp_path):
    gc_maps = tmp_path / "sqmaps" / "gc"
    gc_maps.mkdir(parents=True)
    expected = gc_maps / "267f397274370fc9.webp"
    expected.write_bytes(b"webp-fixture")

    assert _resolve_sqmap(tmp_path / "sqmaps", "267f397274370fc9") == expected


def test_gc_missing_variant_bounds_are_inherited_only_from_unique_map_id(tmp_path):
    data_root = tmp_path / "data" / "static" / "gc"
    data_root.mkdir(parents=True)
    map_record = {
        "mapId": "test-map",
        "mapName": "TestMap",
        "imageUrl": "/maps/gc/test-map.webp",
        "thumbnailUrl": "/maps/gc/test-map.thumb.webp",
        "worldBoundsCm": [-100.0, -200.0, 100.0, 200.0],
    }
    missing_variant = dict(map_record, worldBoundsCm=None)
    (data_root / "map_catalog.json").write_text(json.dumps({
        "layers": {
            "GC_Test_AAS_V1": map_record,
            "GC_Test_AAS_V2": missing_variant,
        },
    }), encoding="utf-8")
    maps = tmp_path / "sqmaps" / "gc"
    maps.mkdir(parents=True)
    (maps / "test-map.webp").write_bytes(b"webp")
    (maps / "test-map.thumb.webp").write_bytes(b"webp")

    report = coverage.verify_static(tmp_path)

    assert report["ok"]
    assert report["summary"]["renderReadyLayers"] == 2
    assert report["summary"]["boundsSources"] == {"layer": 1, "mapId-shared": 1}
    inherited = Metadata.load(tmp_path / "data" / "static").layer_bounds_for("Test AAS V2")
    assert inherited is not None
    assert inherited["boundsSource"] == "mapId-shared"


def test_gc_ambiguous_map_id_does_not_invent_variant_bounds(tmp_path):
    data_root = tmp_path / "data" / "static" / "gc"
    data_root.mkdir(parents=True)
    common = {
        "mapId": "ambiguous",
        "mapName": "Ambiguous",
        "imageUrl": "/maps/gc/ambiguous.webp",
        "thumbnailUrl": "/maps/gc/ambiguous.thumb.webp",
    }
    layers = {
        "GC_Ambiguous_AAS_V1": dict(common, worldBoundsCm=[-100, -100, 100, 100]),
        "GC_Ambiguous_AAS_V2": dict(common, worldBoundsCm=[-200, -200, 200, 200]),
        "GC_Ambiguous_AAS_V3": dict(common, worldBoundsCm=None),
    }
    (data_root / "map_catalog.json").write_text(
        json.dumps({"layers": layers}), encoding="utf-8")
    maps = tmp_path / "sqmaps" / "gc"
    maps.mkdir(parents=True)
    (maps / "ambiguous.webp").write_bytes(b"webp")
    (maps / "ambiguous.thumb.webp").write_bytes(b"webp")

    report = coverage.verify_static(tmp_path)

    assert not report["ok"]
    third = next(item for item in report["layers"]
                 if item["layerId"] == "GC_Ambiguous_AAS_V3")
    assert "ambiguous_bounds" in third["issues"]


def test_gc_conflicting_map_name_alias_is_fail_closed(tmp_path):
    data_root = tmp_path / "data" / "static" / "gc"
    data_root.mkdir(parents=True)
    layers = {}
    for suffix, map_id, texture in (("V1", "map-a", "map-a"),
                                    ("V2", "map-b", "map-b")):
        layers[f"GC_Shared_AAS_{suffix}"] = {
            "mapId": map_id,
            "mapName": "SharedMap",
            "imageUrl": f"/maps/gc/{texture}.webp",
            "thumbnailUrl": f"/maps/gc/{texture}.thumb.webp",
            "worldBoundsCm": [-100, -100, 100, 100],
        }
    (data_root / "map_catalog.json").write_text(
        json.dumps({"layers": layers}), encoding="utf-8")
    maps = tmp_path / "sqmaps" / "gc"
    maps.mkdir(parents=True)
    for texture in ("map-a", "map-b"):
        (maps / f"{texture}.webp").write_bytes(b"webp")
        (maps / f"{texture}.thumb.webp").write_bytes(b"webp")

    metadata = Metadata.load(tmp_path / "data" / "static")

    assert metadata.layer_bounds_for("SharedMap") is None
    assert metadata.layer_bounds_for("Shared AAS V1") is not None
    assert metadata.layer_bounds_for("Shared AAS V2") is not None


def test_runtime_coverage_checks_provider_and_exact_bindings(tmp_path):
    data_root = tmp_path / "data" / "static" / "gc"
    data_root.mkdir(parents=True)
    (data_root / "map_catalog.json").write_text(json.dumps({
        "layers": {
            "GC_Test_AAS_V1": {
                "mapId": "test-map",
                "mapName": "TestMap",
                "imageUrl": "/maps/gc/test-map.webp",
                "thumbnailUrl": "/maps/gc/test-map.thumb.webp",
                "worldBoundsCm": [-100, -100, 100, 100],
            },
        },
    }), encoding="utf-8")
    (tmp_path / "sqmaps" / "gc").mkdir(parents=True)
    (tmp_path / "sqmaps" / "gc" / "test-map.webp").write_bytes(b"webp")
    (tmp_path / "sqmaps" / "gc" / "test-map.thumb.webp").write_bytes(b"webp")
    (tmp_path / "data" / "static" / "asset_providers.json").write_text(json.dumps({
        "schemaVersion": 1,
        "defaultProviderId": "vanilla",
        "providers": {
            "vanilla": {"id": "vanilla", "label": "vanilla"},
            "test": {
                "id": "test", "label": "test",
                "detect": {"gameStateInstanceClasses": ["BP_TestGameState_C"]},
                "roleIcons": {"TEST_Rifleman": "./icons/test/rifle.webp"},
                "vehicleIcons": {"BP_TestVehicle_C": "./icons/test/vehicle.webp"},
                "deployableIcons": {"BP_TestDeployable_C": "./icons/test/deployable.webp"},
                "markerIcons": {"BP_TestMarker_C": "./icons/test/marker.webp"},
                "weaponIcons": {"BP_TestWeapon_C": "./icons/test/weapon.webp"},
            },
        },
    }), encoding="utf-8")
    snap = {
        "gameState": {
            "mapName": "Test AAS V1",
            "instanceClass": "BP_TestGameState_C",
            "layer": {"name": "Test AAS V1"},
        },
        "teams": [],
        "players": [{"roleId": "TEST_Rifleman",
                      "soldier": {"weapon": {"className": "BP_TestWeapon_C"}}}],
        "vehicles": [{"classShort": "BP_TestVehicle_C"}],
        "deployables": [{"classShort": "BP_TestDeployable_C"}],
        "markers": [{"classShort": "BP_TestMarker_C"}],
    }
    snapshot_path = tmp_path / "snapshot.json"
    snapshot_path.write_text(json.dumps(snap), encoding="utf-8")

    report = coverage.verify_runtime(tmp_path, [snapshot_path])

    assert report["ok"]
    assert report["expectedCatalogLayers"] == 1
    assert report["observedCatalogLayers"] == 1
    assert report["unobservedCatalogLayers"] == []
    assert report["providerObservations"] == {"test": 1}
    assert report["unbound"] == {}


def test_gc_coverage_cli_fails_closed_on_incomplete_catalog(tmp_path):
    data_root = tmp_path / "data" / "static" / "gc"
    data_root.mkdir(parents=True)
    (data_root / "map_catalog.json").write_text(json.dumps({
        "layers": {"GC_Incomplete_AAS_V1": {"mapId": "missing"}},
    }), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(Path(coverage.__file__)), "--repo-root", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 1
    assert "missing_bounds" in result.stdout
