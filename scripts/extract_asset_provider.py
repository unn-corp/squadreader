#!/usr/bin/env python3
"""Build a SquadReader asset-provider manifest from a mod's cooked packages.

This is the binding step between the GC Maps extraction tooling and the
viewer.  It deliberately uses ``ue_zen`` and the mod's role DataTables rather
than inferring an icon from a role name.  A different mod can produce the same
provider contract without any frontend changes.

The script emits URLs for decoded assets using the same content-addressed
filename convention as ``GC-config/tooling/extract_map_catalog.py``:
``sha256(cooked asset path)[:16].webp``.  The texture decode itself remains in
the shared CUE4Parse helper; run that helper with the emitted asset requests,
then package the resulting WebPs and this manifest together.

Example::

    PYTHONPATH=/path/to/GC-config/tooling OOZ=/tmp/ooz/oozdec \
      python scripts/extract_asset_provider.py \
        --mod-paks /path/to/GC/Content/Paks/Windows \
        --roles-json data/static/gc/roles.json \
        --out data/static/asset_providers.json

The current repository keeps the four live-replay vehicle bindings explicit:
they came from the captured server class names and the corresponding authored
GC map icons.  The same manifest shape supports additional vehicle,
deployable, marker, and faction bindings as they are extracted.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any


# GC keeps clone and droid role art in sibling HUD trees.  Restricting this to
# the clone directory silently converted every CIS role back to vanilla art.
ROLE_ICON_PREFIX = "/ANE_BASE/Gameplay/HUD/"
GC_ROOT = "/ANE_BASE/"

# These are exact runtime class names observed in the GC replay.  Related
# child blueprints are included only when the authored class is unambiguous;
# adding a class here is a data update, not a renderer code change.
VEHICLE_ICON_ASSETS: dict[str, str] = {
    "BP_LAAT_DEV_C": "/ANE_BASE/Art/Icons/LAAT/LAAT_MapIcon",
    "BP_LAAT_DEV_Blue_C": "/ANE_BASE/Art/Icons/LAAT/LAAT_MapIcon",
    "BP_LAAT_DEV_Blue_Skirmish_C": "/ANE_BASE/Art/Icons/LAAT/LAAT_MapIcon",
    "BP_LAAT_DEV_CIS_C": "/ANE_BASE/Art/Icons/LAAT/LAAT_MapIcon",
    "BP_LAAT_DEV_GE_C": "/ANE_BASE/Art/Icons/LAAT/LAAT_MapIcon",
    "BP_LAAT_DEV_Skirmish_Child_C": "/ANE_BASE/Art/Icons/LAAT/LAAT_MapIcon",
    "BP_LAAT_DEV_Skirmish_Child_GE_C": "/ANE_BASE/Art/Icons/LAAT/LAAT_MapIcon",
    "BP_LAAT_Carrier2_C": "/ANE_BASE/Vehicles/LAAT-C/UI/T_LAAT_C_MapIcon",
    "BP_LAAT_Carrier2_GE_C": "/ANE_BASE/Vehicles/LAAT-C/UI/T_LAAT_C_MapIcon",
    "BP_HMP_dev_C": "/ANE_BASE/Art/Icons/HMP/HMP_MapIcon",
    "BP_HMP_dev_GAR_C": "/ANE_BASE/Art/Icons/HMP/HMP_MapIcon",
    "BP_HMP_Carrier_C": "/ANE_BASE/Art/Icons/HMP/HMPC_MapIcon",
    "BP_GC_LAATLE_C": "/ANE_BASE/Art/Icons/LAATLE/LAATleTop",
    "BP_GC_LAATLE_GE_C": "/ANE_BASE/Art/Icons/LAATLE/LAATleTop",
}


def _load(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _public_url(asset_path: str) -> str:
    digest = hashlib.sha256(asset_path.encode("utf-8")).hexdigest()[:16]
    return f"./icons/gc/{digest}.webp"


def _struct_field(value: Any, field: str) -> Any:
    if not isinstance(value, list):
        return None
    for name, _type, inner in value:
        if name == field:
            return inner
    return None


def _package(index: dict[str, tuple[Any, int]], path: str):
    # UE package paths are case-insensitive, although the TOC spelling is not
    # guaranteed to match a DataTable reference's spelling.
    entry = index.get(path)
    if entry is None:
        folded = path.casefold()
        entry = next((v for k, v in index.items() if k.casefold() == folded), None)
    if entry is None:
        return None
    toc, toc_index = entry
    from ue_zen import ZenPackage  # imported after caller configures PYTHONPATH
    return ZenPackage(toc.read(toc_index))


def _role_record(pkg: Any, stem: str) -> tuple[str | None, str | None]:
    # Most packages use the same export name as the role id.  A few GC
    # variants reuse an export/table row (for example ARC_1/ARC_2), so use the
    # sole data-bearing export as the authoritative fallback instead of
    # treating the package basename as a row-name guess.
    fallback: tuple[str | None, str | None] = (None, None)
    for export_index, export in enumerate(pkg.exports):
        if export.get("name") != stem and len(pkg.exports) != 1:
            continue
        data = pkg.export_dict(export_index).get("Data")
        if not isinstance(data, list):
            continue
        table = _struct_field(data, "DataTable")
        row = _struct_field(data, "RowName") or export.get("name")
        if export.get("name") == stem:
            return table, row
        fallback = (table, row)
    return fallback


def _install_soft_path_support() -> None:
    """Teach the shared parser the cooked 20-byte SoftObjectPath shape.

    GC Maps' common parser already owns tagged-property traversal.  This small
    compatibility layer only adds the one value form needed by role UI icon
    references; 4-byte object references keep their original behavior.
    """
    from ue_zen import ZenPackage, u32

    original = ZenPackage._value

    def value(self: Any, offset: int, size: int, type_name: Any, depth: int):
        if type_name[0] == "SoftObjectProperty" and size >= 16:
            package_path = self.name(u32(self.d, offset))
            if isinstance(package_path, str) and package_path.startswith("/"):
                return package_path
            return None
        return original(self, offset, size, type_name, depth)

    ZenPackage._value = value


def _role_bindings(index: dict[str, tuple[Any, int]], roles: dict[str, Any]) -> tuple[dict[str, str], dict[str, str], list[str]]:
    from ue_zen import datatable_rows

    role_icons: dict[str, str] = {}
    role_sources: dict[str, str] = {}
    unresolved: list[str] = []
    table_cache: dict[str, dict[str, Any]] = {}
    for role_id, record in sorted((roles.get("roles") or {}).items()):
        if not isinstance(record, dict):
            continue
        package_path = record.get("path")
        if not isinstance(package_path, str) or not package_path.startswith(GC_ROOT):
            continue
        role_pkg = _package(index, package_path)
        if role_pkg is None:
            unresolved.append(f"role package missing: {package_path}")
            continue
        table_path, row_name = _role_record(role_pkg, role_id)
        if not isinstance(table_path, str) or not isinstance(row_name, str):
            unresolved.append(f"role DataTable reference missing: {role_id}")
            continue
        table_key = table_path.casefold()
        if table_key not in table_cache:
            table_pkg = _package(index, table_path)
            if table_pkg is None:
                table_cache[table_key] = {}
            else:
                try:
                    table_cache[table_key] = datatable_rows(table_pkg)
                except Exception as exc:  # fail closed per role, keep report
                    unresolved.append(f"role DataTable unreadable: {table_path}: {exc}")
                    table_cache[table_key] = {}
        row = table_cache[table_key].get(row_name)
        icon_asset = row.get("UI_Icon") if isinstance(row, dict) else None
        if not isinstance(icon_asset, str) or not icon_asset.startswith(ROLE_ICON_PREFIX):
            unresolved.append(f"role icon reference missing: {role_id}")
            continue
        role_icons[role_id] = _public_url(icon_asset)
        role_sources[role_id] = icon_asset
    return role_icons, role_sources, unresolved


def _vehicle_bindings() -> tuple[dict[str, str], dict[str, str]]:
    return (
        {cls: _public_url(asset) for cls, asset in sorted(VEHICLE_ICON_ASSETS.items())},
        dict(sorted(VEHICLE_ICON_ASSETS.items())),
    )


def build(
    mod_paks: Path,
    roles_path: Path,
    provider_id: str,
    tooling_dir: Path | None = None,
) -> dict[str, Any]:
    tooling_dir = tooling_dir or (Path(__file__).resolve().parents[2] / "GC-config" / "tooling")
    if str(tooling_dir) not in sys.path:
        sys.path.insert(0, str(tooling_dir))
    from ue_zen import build_index

    index, _tocs = build_index([mod_paks])
    roles = _load(roles_path)
    _install_soft_path_support()
    role_icons, role_sources, unresolved = _role_bindings(index, roles)
    vehicle_icons, vehicle_sources = _vehicle_bindings()

    role_prefixes = sorted({role_id.split("_", 1)[0] + "_" for role_id in role_icons})
    faction_prefixes = sorted({role_id.split("_", 1)[0] for role_id in role_icons})
    provider = {
        "id": provider_id,
        "label": "Galactic Contention",
        "version": "local-cooked-assets",
        "assetRoot": "./icons/gc",
        "detect": {
            "gameStateInstanceClasses": ["BP_GameStateGC_C"],
            "factionPrefixes": faction_prefixes,
            "rolePrefixes": role_prefixes,
            "vehicleClassPrefixes": ["BP_LAAT_", "BP_HMP_", "BP_GC_LAATLE_"],
        },
        "roleIcons": role_icons,
        "vehicleIcons": vehicle_icons,
        "deployableIcons": {},
        "markerIcons": {},
        "factionIcons": {},
        "sourceAssets": {
            "roleIcons": role_sources,
            "vehicleIcons": vehicle_sources,
        },
        "unresolvedAssets": sorted(set(unresolved)),
    }
    return {
        "schemaVersion": 1,
        "defaultProviderId": "vanilla",
        "providers": {
            "vanilla": {
                "id": "vanilla",
                "label": "Squad (vanilla)",
                "version": "builtin",
            },
            provider_id: provider,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mod-paks", type=Path, required=True)
    parser.add_argument("--roles-json", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--provider-id", default="gc")
    parser.add_argument(
        "--tooling-dir",
        type=Path,
        help="GC Maps tooling directory containing ue_zen.py (defaults to sibling GC-config/tooling)",
    )
    args = parser.parse_args()
    catalog = build(
        args.mod_paks.resolve(),
        args.roles_json.resolve(),
        args.provider_id,
        args.tooling_dir.resolve() if args.tooling_dir else None,
    )
    _write(args.out.resolve(), catalog)
    provider = catalog["providers"][args.provider_id]
    print(
        f"asset provider {args.provider_id}: "
        f"{len(provider['roleIcons'])} role bindings, "
        f"{len(provider['vehicleIcons'])} vehicle bindings, "
        f"{len(provider['unresolvedAssets'])} unresolved"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
