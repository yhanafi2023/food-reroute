"use client";
import type { Tracking } from "./types";
import { usePoll } from "./usePoll";

// Live driver position + ETA to the viewer's own location, refreshed every 3 seconds.
export function useTracking(deliveryId: number | null | undefined, active = true) {
  return usePoll<Tracking>(deliveryId && active ? `/deliveries/${deliveryId}/tracking` : null, 3000);
}
