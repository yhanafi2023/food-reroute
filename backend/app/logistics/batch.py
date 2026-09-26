"""run_batch: match many open rescues at once, earliest pickup deadline first.

Greedy: pop rescues from a min heap keyed by deadline, give each one its best
available driver, then remove that driver and reduce the needs it filled before
the next rescue. O(R log R) for the heap plus R calls to find_best_match, each
O(D log k + N log k) for the prefilter and O(k^2) for scoring.

Greedy is fast and easy to explain, but not globally optimal: an early rescue can
take a driver that a later rescue needed more. The upgrade path is the Hungarian
algorithm (scipy.optimize.linear_sum_assignment) on an R x D cost matrix of match
scores, which is O(n^3).
"""
from __future__ import annotations

import heapq
from datetime import datetime
from typing import Any, Dict, List, Optional

from app.logistics.matching import find_best_match, parse_time


def run_batch(
    rescues: List[Dict[str, Any]],
    drivers: List[Dict[str, Any]],
    needs: List[Dict[str, Any]],
    now: Optional[datetime] = None,
) -> List[Dict[str, Any]]:
    far_future = float("inf")
    heap = []
    for i, r in enumerate(rescues):
        deadline = parse_time(r.get("pickup_deadline"))
        heapq.heappush(heap, (deadline.timestamp() if deadline else far_future, i, r))

    needs = [dict(n) for n in needs]  # local copies; fulfilment is tracked per batch
    used_drivers = set()
    matches = []
    while heap:
        _, _, rescue = heapq.heappop(heap)
        match = find_best_match(rescue, drivers, needs, exclude_driver_ids=used_drivers, now=now)
        if match is None:
            continue
        used_drivers.add(match["driver"]["id"])
        by_id = {n["id"]: n for n in needs}
        for stop in match["stops"]:
            need = by_id[stop["need_id"]]
            need["meals_fulfilled"] = int(need.get("meals_fulfilled") or 0) + stop["meals"]
        matches.append(match)
    return matches
