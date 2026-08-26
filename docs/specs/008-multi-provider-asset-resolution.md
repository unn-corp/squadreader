# Multi-provider asset resolution

Status: implemented for the captured GC replay; the provider contract is
intended for any Squad mod.

## Goal

The viewer must choose between vanilla Squad assets and a mod's assets from
runtime evidence. A mod is not a special case in the renderer. It supplies a
namespaced, data-only provider manifest; the same interface can later carry
vehicle, kit, weapon, deployable, marker, faction, and map assets.

## Contract

`data/static/asset_providers.json` contains:

```json
{
  "schemaVersion": 1,
  "defaultProviderId": "vanilla",
  "providers": {
    "vanilla": { "id": "vanilla", "label": "Squad (vanilla)" },
    "example-mod": {
      "id": "example-mod",
      "label": "Example Mod",
      "assetRoot": "./icons/example-mod",
      "detect": {
        "gameStateInstanceClasses": ["BP_ExampleGameState_C"],
        "factionPrefixes": ["EX_"],
        "rolePrefixes": ["EX_"],
        "vehicleClassPrefixes": ["BP_EX_"]
      },
      "roleIcons": { "EX_Rifleman": "./icons/example-mod/rifleman.webp" },
      "vehicleIcons": { "BP_EX_Tank_C": "./icons/example-mod/tank.webp" },
      "deployableIcons": {},
      "markerIcons": {},
      "factionIcons": {}
    }
  }
}
```

Provider asset URLs are always namespaced. This prevents a mod asset from
shadowing `icons/roles`, and lets several providers coexist in one viewer.
The maps are keyed by exact runtime identifiers. Prefixes are detection hints,
not icon substitutions.

## Selection and fallback

1. A valid `gameState.assetProviderId` emitted by the backend wins.
2. Otherwise the frontend scores registered providers from the game-state
   class, exact role/vehicle bindings, faction identifiers, and declared
   prefixes.
3. An exact binding from the selected provider wins for that entity.
4. If the selected provider has no binding, the existing vanilla resolver is
   used as the explicit compatibility fallback.
5. If no provider has evidence, the registry's `defaultProviderId` is used.

The frontend also searches exact role bindings when a panel only has a role ID,
which keeps older recordings usable. When a complete snapshot is available it
is passed into every resolver; this prevents an overlapping identifier from
silently borrowing an icon from a different mod.

## GC extraction

`scripts/extract_asset_provider.py` imports the shared GC Maps
`tooling/ue_zen.py` reader and follows each GC role's `DataTable` and `RowName`
to the authored `UI_Icon` `FSoftObjectPath`. It does not infer a role icon from
tokens such as `SL`, `Medic`, or `Pilot`. The CUE4Parse texture helper from GC
Maps decodes the referenced client textures; the content-addressed output name
is `sha256(assetPath)[:16].webp`.

The current generated provider has 883 exact GC role bindings and 14 exact
vehicle bindings. It includes the captured classes `BP_LAAT_DEV_C`,
`BP_LAAT_Carrier2_C`, `BP_HMP_dev_C`, and `BP_HMP_Carrier_C`, mapped to the
authored LAAT, LAAT-C, HMP, and HMP carrier map icons respectively. A missing
binding is recorded as unresolved instead of being guessed.

Rebuild the provider against a local client package set with:

```bash
OOZ=/tmp/ooz/oozdec .venv/bin/python scripts/extract_asset_provider.py \
  --tooling-dir /path/to/GC-config/tooling \
  --mod-paks /path/to/mod/Content/Paks/Windows \
  --roles-json data/static/gc/roles.json \
  --out data/static/asset_providers.json
```

Then decode the provider's `sourceAssets` with the shared
`cue_texture_exporter`, add the derived WebPs to the artifact, package, and
run `python scripts/verify_gc_asset_bundle.py`.

## Runtime wiring

- The backend loads the registry from the configured static data directory and
  emits `GET /api/asset-providers`.
- New snapshots carry `gameState.assetProviderId`; old snapshots are detected
  client-side from their existing runtime fields.
- The canvas and role-bearing UI panels use the same resolver contract.
- `icons/gc/` and `sqmaps/gc/` remain separate from vanilla assets.

## Acceptance tests

- A GC replay containing `GAR_P1_SL_Pilot` requests the GC `leadpilot` asset,
  never `T_role_pilot_squadleader.png`.
- `BP_LAAT_DEV_C` and `BP_LAAT_Carrier2_C` request LAAT artwork, never the CIS
  logo or a generic transport icon.
- A vanilla snapshot still resolves through the existing vanilla ladder.
- A registered provider with no exact binding falls back to vanilla without
  borrowing a different mod's icon.
- Adding a second provider manifest requires no change to `icons.ts`.
