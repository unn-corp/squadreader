// Runtime asset-provider registry.
//
// Vanilla Squad remains the renderer's built-in fallback. Mods contribute
// data-only provider manifests with exact runtime-class/role bindings and
// namespaced public URLs. This keeps a new mod out of icons.ts and lets old
// recordings continue to render even before the server-side selector field
// existed.

import { useSyncExternalStore } from "react";
import type { Snapshot } from "../state/types";

export type AssetMap = Record<string, string>;

export interface AssetProviderDetection {
  gameStateInstanceClasses?: string[];
  factionPrefixes?: string[];
  rolePrefixes?: string[];
  vehicleClassPrefixes?: string[];
}

export interface AssetProvider {
  id: string;
  label: string;
  version?: string;
  assetRoot?: string;
  detect?: AssetProviderDetection;
  roleIcons?: AssetMap;
  vehicleIcons?: AssetMap;
  deployableIcons?: AssetMap;
  markerIcons?: AssetMap;
  factionIcons?: AssetMap;
}

export interface AssetProviderCatalog {
  schemaVersion: 1;
  defaultProviderId: string;
  providers: Record<string, AssetProvider>;
}

export const VANILLA_PROVIDER: AssetProvider = {
  id: "vanilla",
  label: "Squad (vanilla)",
  version: "builtin",
};

const BUILTIN_CATALOG: AssetProviderCatalog = {
  schemaVersion: 1,
  defaultProviderId: "vanilla",
  providers: { vanilla: VANILLA_PROVIDER },
};

let catalog = BUILTIN_CATALOG;
let request: Promise<AssetProviderCatalog> | null = null;
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

function emit(): void {
  for (const listener of listeners) listener();
}

function validCatalog(value: unknown): value is AssetProviderCatalog {
  if (!value || typeof value !== "object") return false;
  const raw = value as Partial<AssetProviderCatalog>;
  return raw.schemaVersion === 1
    && typeof raw.defaultProviderId === "string"
    && !!raw.providers
    && typeof raw.providers === "object"
    && raw.defaultProviderId in raw.providers;
}

export function getAssetProviderCatalog(): AssetProviderCatalog {
  return catalog;
}

// Components that show a role icon subscribe so a provider fetched after
// first paint replaces the initial vanilla fallback without a page reload.
export function useAssetProviders(): AssetProviderCatalog {
  return useSyncExternalStore(subscribe, getAssetProviderCatalog, getAssetProviderCatalog);
}

export async function loadAssetProviders(): Promise<AssetProviderCatalog> {
  if (request) return request;
  request = fetch("./api/asset-providers", { cache: "no-store" })
    .then(async (response) => {
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const next: unknown = await response.json();
      if (!validCatalog(next)) throw new Error("invalid asset provider manifest");
      catalog = next;
      emit();
      return catalog;
    })
    .catch(() => catalog);
  return request;
}

function prefixMatch(value: string | null | undefined, prefixes: string[] | undefined): boolean {
  return !!value && !!prefixes?.some((prefix) => value.startsWith(prefix));
}

function providerScore(provider: AssetProvider, snap: Snapshot): number {
  const detect = provider.detect;
  if (!detect) return 0;
  let score = 0;
  const gs = snap.gameState;
  if (gs?.instanceClass
      && detect.gameStateInstanceClasses?.includes(gs.instanceClass)) score += 100;
  for (const p of snap.players ?? []) {
    if (p.roleId && provider.roleIcons?.[p.roleId]) score += 25;
    if (prefixMatch(p.roleId, detect.rolePrefixes)) score += 10;
  }
  for (const v of snap.vehicles ?? []) {
    if (v.classShort && provider.vehicleIcons?.[v.classShort]) score += 25;
    if (prefixMatch(v.classShort, detect.vehicleClassPrefixes)) score += 10;
  }
  for (const team of snap.teams ?? []) {
    if (prefixMatch(team.factionId, detect.factionPrefixes)) score += 15;
  }
  return score;
}

export function selectAssetProvider(
  snap: Snapshot | null | undefined,
  source: AssetProviderCatalog = catalog,
): AssetProvider {
  const explicit = snap?.gameState?.assetProviderId;
  if (explicit && source.providers[explicit]) return source.providers[explicit]!;

  let best: AssetProvider | null = null;
  let bestScore = 0;
  for (const [id, candidate] of Object.entries(source.providers)) {
    if (id === source.defaultProviderId) continue;
    const score = providerScore(candidate, snap ?? ({} as Snapshot));
    if (score > bestScore) {
      best = candidate;
      bestScore = score;
    }
  }
  return best ?? source.providers[source.defaultProviderId] ?? VANILLA_PROVIDER;
}

type AssetBucket = "roleIcons" | "vehicleIcons" | "deployableIcons" | "markerIcons" | "factionIcons";

// Entity panels do not always have the full Snapshot. Exact bindings are
// therefore also searched directly, which makes kill-feed and scoreboard
// icons correct for older GC recordings with no assetProviderId field.
export function assetUrl(
  bucket: AssetBucket,
  key: string | null | undefined,
  snap?: Snapshot | null,
  source: AssetProviderCatalog = catalog,
): string | null {
  if (!key) return null;
  const selected = snap ? selectAssetProvider(snap, source) : null;
  if (selected) {
    const hit = selected[bucket]?.[key];
    if (hit) return hit;
    // A full snapshot has already selected its active mod. Do not borrow an
    // icon from a different registered mod when this provider lacks a
    // binding; the caller's explicit vanilla fallback remains authoritative.
    return null;
  }
  for (const provider of Object.values(source.providers)) {
    if (provider.id === source.defaultProviderId || provider === selected) continue;
    const hit = provider[bucket]?.[key];
    if (hit) return hit;
  }
  return null;
}
