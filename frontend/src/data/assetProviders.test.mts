import {
  assetUrl,
  selectAssetProvider,
  type AssetProviderCatalog,
} from "./assetProviders";
import type { Snapshot } from "../state/types";

function ok(condition: unknown, message: string): void {
  if (!condition) throw new Error(message);
}

const catalog: AssetProviderCatalog = {
  schemaVersion: 1,
  defaultProviderId: "vanilla",
  providers: {
    vanilla: { id: "vanilla", label: "Squad" },
    alpha: {
      id: "alpha",
      label: "Alpha mod",
      detect: {
        gameStateInstanceClasses: ["BP_AlphaGameState_C"],
        rolePrefixes: ["ALPHA_"],
      },
      roleIcons: { ALPHA_SL: "./icons/alpha/sl.webp" },
    },
    beta: {
      id: "beta",
      label: "Beta mod",
      roleIcons: { OVERLAP: "./icons/beta/overlap.webp" },
    },
  },
};

const snapshot = {
  gameState: {
    instanceClass: "BP_AlphaGameState_C",
    assetProviderId: null,
  },
  teams: [], players: [{ roleId: "ALPHA_SL" }], vehicles: [],
} as unknown as Snapshot;

ok(selectAssetProvider(snapshot, catalog).id === "alpha", "runtime class selects mod");
ok(assetUrl("roleIcons", "ALPHA_SL", snapshot, catalog) === "./icons/alpha/sl.webp",
  "selected provider exact binding wins");
ok(assetUrl("roleIcons", "OVERLAP", snapshot, catalog) === null,
  "selected provider does not borrow another mod");
ok(assetUrl("roleIcons", "OVERLAP", null, catalog) === "./icons/beta/overlap.webp",
  "panel-only exact lookup finds a registered provider");
ok(selectAssetProvider({ gameState: null, teams: [], players: [], vehicles: [] } as unknown as Snapshot, catalog).id === "vanilla",
  "unknown snapshot uses vanilla default");

console.log("asset provider tests passed");
