"""Regression coverage for GC's Blueprint-derived runtime classes."""

import json

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


def test_gc_map_texture_resolves_from_packaged_subdirectory(tmp_path):
    gc_maps = tmp_path / "sqmaps" / "gc"
    gc_maps.mkdir(parents=True)
    expected = gc_maps / "267f397274370fc9.webp"
    expected.write_bytes(b"webp-fixture")

    assert _resolve_sqmap(tmp_path / "sqmaps", "267f397274370fc9") == expected
