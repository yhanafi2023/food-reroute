"use client";
import { useEffect, useState } from "react";
import { api } from "./api";
import type { CensusArea } from "./types";

let cache: CensusArea[] | null = null;
let tried = false;

// Census tracts for the community-need layer (a073982), loaded once and cached. The backend route
// GET /community-need/areas is not on any branch yet; until it exists this returns [] (one request
// per page session) and maps simply do not offer the layer.
export function useCommunityNeedAreas(enabled = true): CensusArea[] {
  const [areas, setAreas] = useState<CensusArea[] | null>(cache);
  useEffect(() => {
    if (!enabled || cache || tried) return;
    tried = true;
    api<{ areas: CensusArea[] }>("/community-need/areas")
      .then((r) => {
        cache = r.areas;
        setAreas(r.areas);
      })
      .catch(() => undefined);
  }, [enabled]);
  return enabled ? (areas ?? []) : [];
}
