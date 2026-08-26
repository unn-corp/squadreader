"""
Static metadata loader for Squad display-name enrichment.

Pulls four JSON files from squadreplay.com (cached locally under
sqreader/data/static/). The reader uses them to attach small
display-friendly hints onto each snapshot WITHOUT bloating the
NDJSON line — most metadata tables are sent to the frontend once
separately, only per-entity lookups land in the per-tick output.

Source URLs (downloaded once, hand-refresh on Squad updates):
  https://cota.squadreplay.com/squad_pools.json
  https://cota.squadreplay.com/static/data/vehicle_factions.json
  https://cota.squadreplay.com/api/map-config
  https://cota.squadreplay.com/api/layer-bounds

A fifth table, capzones.json (static cap-zone geometry), is produced locally
by scripts/fetch_capzones.py from SquadCalc rather than downloaded here.

This module is intentionally read-only and side-effect free at import
time. Callers do `meta = load_metadata()` once at startup.
"""
from __future__ import annotations

import json
import math
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


def _default_data_dir() -> Path:
    """Locate ``data/static``, in a source tree *or* a compiled binary.

    Source layout puts it two levels above this module. A Nuitka onefile build
    unpacks the bundled copy next to the module tree, which usually lines up —
    but ``__file__`` inside an extracted onefile is not something to bet the
    map rendering on, and a miss here fails *silently*: `_load_json` returns
    None for every table, metadata comes back empty, and maps just don't
    render with nothing in the log to explain it.

    So try the candidates in order and return the first that really exists,
    falling back to the source-relative guess so behaviour is unchanged when
    nothing is bundled.
    """
    here = Path(__file__).resolve()
    candidates = [here.parents[2] / "data" / "static"]
    # Compiled: alongside the executable, and alongside the extraction root.
    if getattr(sys, "frozen", False) or "__compiled__" in globals():
        exe = Path(sys.executable).resolve().parent
        candidates += [exe / "data" / "static",
                       here.parents[1] / "data" / "static"]
    # Explicit escape hatch for odd deployments.
    env = os.environ.get("SQREADER_DATA_DIR")
    if env:
        candidates.insert(0, Path(env))
    for c in candidates:
        if c.is_dir():
            return c
    return candidates[-1] if env else here.parents[2] / "data" / "static"


DEFAULT_DATA_DIR = _default_data_dir()


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _normalise_layer_key(value: str) -> str:
    """Make UE/display layer names comparable without guessing words."""
    return "".join(ch.lower() for ch in value if ch.isalnum())


def _valid_world_bounds(value: Any) -> tuple[float, float, float, float] | None:
    """Return finite, ordered bounds, rejecting malformed extraction output."""
    if not isinstance(value, list) or len(value) != 4:
        return None
    if any(isinstance(v, bool) or not isinstance(v, (int, float))
           or not math.isfinite(float(v)) for v in value):
        return None
    bounds = (float(value[0]), float(value[1]), float(value[2]), float(value[3]))
    if bounds[0] >= bounds[2] or bounds[1] >= bounds[3]:
        return None
    return bounds


def _gc_layer_record(
    layer_id: str,
    raw: dict[str, Any],
    inherited_bounds: tuple[float, float, float, float] | None = None,
) -> dict[str, Any] | None:
    """Adapt one GC Maps catalog layer to SquadReader's layer schema."""
    bounds = _valid_world_bounds(raw.get("worldBoundsCm"))
    bounds_source = "layer"
    if bounds is None and inherited_bounds is not None:
        # A layer variant can omit its GLD package even though the catalog has
        # an exact mapId match with another variant. Reusing bounds is safe only
        # when that mapId has one and only one authoritative bounds tuple; the
        # loader computes that condition before calling us.
        bounds = inherited_bounds
        bounds_source = "mapId-shared"
    image_url = raw.get("imageUrl")
    if bounds is None or not isinstance(image_url, str) or not image_url:
        # A catalog entry without imagery cannot be rendered by the replay
        # canvas, so leave it unavailable rather than inventing a texture.
        return None
    min_x, min_y, max_x, max_y = (float(v) for v in bounds)
    texture = Path(image_url).stem
    map_id = raw.get("mapId") or texture
    map_name = raw.get("mapName") or layer_id.removeprefix("GC_")
    game_mode = raw.get("gameMode")
    if not isinstance(game_mode, str) or not game_mode:
        for mode in ("RAAS", "RINV", "AAS", "SKM", "TC", "INV"):
            if f"_{mode}_" in layer_id or layer_id.endswith(f"_{mode}"):
                game_mode = mode
                break
    return {
        "mapId": map_id,
        "mapName": map_name,
        "gameMode": game_mode,
        "texture": texture,
        "topLeft": {"x": min_x, "y": min_y},
        "bottomRight": {"x": max_x, "y": max_y},
        "boundsSource": bounds_source,
    }


@dataclass
class Metadata:
    # Raw tables (kept around so callers can pass them to the frontend
    # once at session start; never re-emitted per snapshot).
    vehicle_factions: dict[str, list[str]] = field(default_factory=dict)
    squad_pools: dict[str, Any] = field(default_factory=dict)
    map_config: dict[str, Any] = field(default_factory=dict)
    layer_bounds: dict[str, Any] = field(default_factory=dict)
    # Static cap-zone geometry per layer, produced offline by
    # scripts/fetch_capzones.py from SquadCalc. Keyed by full display layer
    # name (same keys as layer_bounds). Missing file → {} → merge is a no-op.
    capzones: dict[str, Any] = field(default_factory=dict)
    # GC Maps' extracted catalogs are kept separate from stock Squad metadata;
    # layer lookup below normalises the runtime FText name against this index.
    gc_layer_bounds: dict[str, dict[str, Any]] = field(default_factory=dict)
    gc_roles: dict[str, Any] = field(default_factory=dict)
    # Data-driven asset providers.  The default provider is vanilla; mod
    # providers are generated from their cooked package references and loaded
    # without changing the renderer.
    asset_provider_catalog: dict[str, Any] = field(default_factory=dict)

    # Derived reverse indices, built once at construction:
    _role_keyword_to_pool: dict[str, tuple[str, str]] = field(default_factory=dict)
    # vehicle_pools sub-table: { short_key: kind } e.g. {"2A6_Desert": "MBT"}
    _vehicle_pools: dict[str, str] = field(default_factory=dict)

    @classmethod
    def load(cls, data_dir: Path | None = None) -> "Metadata":
        d = data_dir or DEFAULT_DATA_DIR
        gc_root = d / "gc"
        if not gc_root.is_dir() and (d / "map_catalog.json").is_file():
            # Useful for an operator-provided data directory that points
            # directly at the extracted GC catalog root.
            gc_root = d
        m = cls(
            vehicle_factions=_load_json(d / "vehicle_factions.json") or {},
            squad_pools=_load_json(d / "squad_pools.json") or {},
            map_config=_load_json(d / "map_config.json") or {},
            layer_bounds=_load_json(d / "layer_bounds.json") or {},
            capzones=_load_json(d / "capzones.json") or {},
            gc_roles=_load_json(gc_root / "roles.json") or {},
            asset_provider_catalog=_load_json(d / "asset_providers.json") or {},
        )
        gc_catalog = _load_json(gc_root / "map_catalog.json") or {}
        gc_layers = gc_catalog.get("layers") or {}
        # Build a conservative inheritance index.  mapId is the extracted
        # content identity for the tactical texture; it is stronger than a
        # map-name or layer-name similarity.  Ambiguous bounds are deliberately
        # not inherited.
        map_bounds: dict[str, set[tuple[float, float, float, float]]] = {}
        for raw in gc_layers.values():
            if not isinstance(raw, dict):
                continue
            map_id = raw.get("mapId")
            bounds = _valid_world_bounds(raw.get("worldBoundsCm"))
            if isinstance(map_id, str) and bounds is not None:
                map_bounds.setdefault(map_id, set()).add(bounds)

        alias_records: dict[str, tuple[tuple[Any, ...], dict[str, Any]]] = {}
        alias_conflicts: set[str] = set()
        for layer_id, raw in gc_layers.items():
            if not isinstance(layer_id, str) or not isinstance(raw, dict):
                continue
            map_id = raw.get("mapId")
            bounds = _valid_world_bounds(raw.get("worldBoundsCm"))
            candidates = map_bounds.get(map_id, set()) if isinstance(map_id, str) else set()
            inherited = next(iter(candidates)) if bounds is None and len(candidates) == 1 else None
            record = _gc_layer_record(layer_id, raw, inherited)
            if record is None:
                continue
            aliases = [
                layer_id,
                layer_id.removeprefix("GC_"),
                raw.get("displayName"),
                raw.get("mapName"),
            ]
            identity = (
                record.get("mapId"), record.get("texture"),
                record.get("topLeft", {}).get("x"),
                record.get("topLeft", {}).get("y"),
                record.get("bottomRight", {}).get("x"),
                record.get("bottomRight", {}).get("y"),
            )
            for alias in aliases:
                if isinstance(alias, str) and alias:
                    key = _normalise_layer_key(alias)
                    if not key or key in alias_conflicts:
                        continue
                    previous = alias_records.get(key)
                    if previous is not None and previous[0] != identity:
                        # Do not silently let one map win a shared alias such
                        # as Tatooine. Full layer IDs remain available.
                        alias_conflicts.add(key)
                        alias_records.pop(key, None)
                    elif previous is None:
                        alias_records[key] = (identity, record)
            map_id = record.get("mapId")
            if isinstance(map_id, str):
                m.map_config.setdefault(map_id, record)
        m.gc_layer_bounds = {
            key: value[1] for key, value in alias_records.items()
        }
        # Build derived indices
        for pool_key, pool in (m.squad_pools.get("infantryPools") or {}).items():
            label = pool.get("label") or pool_key
            for role_kw in pool.get("roles", []):
                m._role_keyword_to_pool[role_kw.lower()] = (pool_key, label)
        # Also fold the pool key itself in lowercase as a fallback
        # (so "LAT" in "USMC_LAT_01" matches infantryPools["LAT"] directly).
        for pool_key, pool in (m.squad_pools.get("infantryPools") or {}).items():
            m._role_keyword_to_pool.setdefault(
                pool_key.lower(), (pool_key, pool.get("label") or pool_key))
        m._vehicle_pools = m.squad_pools.get("vehiclePools") or {}
        return m

    # ---- per-entity lookups (used at snapshot time) -----------------------

    def vehicle_faction(self, class_short: str | None) -> list[str] | None:
        if not class_short:
            return None
        # vehicle_factions is keyed by exact BP class name including _C suffix
        return self.vehicle_factions.get(class_short)

    def vehicle_kind(self, class_short: str | None) -> str | None:
        """Returns the high-level kind ('MBT', 'APC', 'Transport', ...)."""
        if not class_short:
            return None
        # vehiclePools is keyed by short name: BP_<short>_C
        if class_short.startswith("BP_") and class_short.endswith("_C"):
            short = class_short[3:-2]
            kind = self._vehicle_pools.get(short)
            if kind:
                return kind
        return None

    def role_pool(self, role_id: str | None) -> dict[str, str] | None:
        """
        Map a Squad role FName (e.g. 'USMC_LAT_01' / 'USMC_Rifleman_01')
        to its infantry pool ({key, label}). Returns None if unrecognized.

        Strategy: tokenize by '_' and check each token (lowercased) against
        the reverse index built from infantryPools.{roles, key-as-self}.
        """
        if not role_id or role_id == "None":
            return None
        gc_role = (self.gc_roles.get("roles") or {}).get(role_id)
        if isinstance(gc_role, dict):
            unit = gc_role.get("unit")
            if isinstance(unit, str) and unit:
                return {"key": unit.replace("/", "_"), "label": unit}
        for tok in role_id.split("_"):
            hit = self._role_keyword_to_pool.get(tok.lower())
            if hit:
                key, label = hit
                return {"key": key, "label": label}
        return None

    def map_bounds(self, map_id: str | None) -> dict[str, Any] | None:
        if not map_id:
            return None
        return self.map_config.get(map_id)

    def layer_bounds_for(self, layer_name: str | None) -> dict[str, Any] | None:
        if not layer_name:
            return None
        return (self.layer_bounds.get(layer_name)
                or self.gc_layer_bounds.get(_normalise_layer_key(layer_name)))

    def capzones_for(self, layer_name: str | None) -> list[dict[str, Any]]:
        """Static cap-zone points for a layer, or [] if none/unknown.

        Keyed identically to layer_bounds (full display layer name), so the
        caller passes the same game_state["mapName"] it uses for bounds — no
        RawLayerKey conversion at runtime (that happens once, offline).
        """
        if not layer_name:
            return []
        pts = self.capzones.get(layer_name)
        return pts if isinstance(pts, list) else []

    def asset_providers(self) -> dict[str, Any]:
        """Return the provider registry for the HTTP bootstrap endpoint."""
        catalog = self.asset_provider_catalog
        if not isinstance(catalog, dict) or not isinstance(catalog.get("providers"), dict):
            return {
                "schemaVersion": 1,
                "defaultProviderId": "vanilla",
                "providers": {
                    "vanilla": {
                        "id": "vanilla",
                        "label": "Squad (vanilla)",
                        "version": "builtin",
                    }
                },
            }
        return catalog

    @staticmethod
    def _matches_prefix(value: Any, prefixes: Any) -> bool:
        return (isinstance(value, str)
                and any(isinstance(prefix, str) and value.startswith(prefix)
                        for prefix in (prefixes if isinstance(prefixes, list) else [])))

    def asset_provider_id(
        self,
        game_state: dict[str, Any] | None,
        teams: list[dict[str, Any]],
        players: list[dict[str, Any]],
        vehicles: list[dict[str, Any]],
    ) -> str | None:
        """Select the best registered provider for one snapshot.

        Explicit snapshot metadata wins.  Otherwise providers score only
        positive evidence from runtime identifiers: game-state class, faction
        id, exact role/vehicle bindings, and declared prefixes.  No provider
        is selected from a display name or from a generic ``BP_`` heuristic.
        """
        catalog = self.asset_providers()
        providers = catalog.get("providers", {})
        if not isinstance(providers, dict):
            return None
        explicit = game_state.get("assetProviderId") if isinstance(game_state, dict) else None
        if isinstance(explicit, str) and explicit in providers:
            return explicit

        role_ids = {
            p.get("roleId") for p in players if isinstance(p, dict)
            and isinstance(p.get("roleId"), str)
        }
        faction_ids = {
            t.get("factionId") for t in teams if isinstance(t, dict)
            and isinstance(t.get("factionId"), str)
        }
        vehicle_classes = {
            v.get("classShort") for v in vehicles if isinstance(v, dict)
            and isinstance(v.get("classShort"), str)
        }
        instance_class = game_state.get("instanceClass") if isinstance(game_state, dict) else None
        best_id: str | None = None
        best_score = 0
        for provider_id, provider in providers.items():
            if not isinstance(provider, dict) or provider_id == catalog.get("defaultProviderId"):
                continue
            detect = provider.get("detect")
            if not isinstance(detect, dict):
                continue
            score = 0
            if (isinstance(instance_class, str)
                    and instance_class in (detect.get("gameStateInstanceClasses") or [])):
                score += 100
            score += sum(25 for role in role_ids
                         if role in (provider.get("roleIcons") or {}))
            score += sum(25 for cls in vehicle_classes
                         if cls in (provider.get("vehicleIcons") or {}))
            score += sum(15 for faction in faction_ids
                         if self._matches_prefix(faction, detect.get("factionPrefixes")))
            if any(self._matches_prefix(role, detect.get("rolePrefixes")) for role in role_ids):
                score += 10
            if any(self._matches_prefix(cls, detect.get("vehicleClassPrefixes"))
                   for cls in vehicle_classes):
                score += 10
            if score > best_score:
                best_id, best_score = provider_id, score
        if best_id:
            return best_id
        default = catalog.get("defaultProviderId")
        return default if isinstance(default, str) and default in providers else None


__all__ = ["Metadata", "DEFAULT_DATA_DIR"]
