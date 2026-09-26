"use client";
import { useEffect, useState } from "react";
import { api } from "./api";
import type { CensusArea } from "./types";

let cache: CensusArea[] | null = null;

// Loaded once and cached: the same 123 Census tracts back every map on the site.
export function useCommunityNeedAreas() {
  const [areas, setAreas] = useState<CensusArea[] | null>(cache);
  useEffect(() => {
    if (cache) return;
    api<{ areas: CensusArea[] }>("/community-need/areas").then((r) => { cache = r.areas; setAreas(r.areas); }).catch(() => undefined);
  }, []);
  return areas ?? [];
}
