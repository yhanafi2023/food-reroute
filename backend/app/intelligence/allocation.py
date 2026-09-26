"""Split one food rescue across the community organizations that need it.

Why greedy by priority fits here:
  * The logistics prefilter hands us at most ~5 candidate needs, and a single
    driver trip carries at most MAX_STOPS drop offs, so the search space is tiny.
  * The business rule is lexicographic: serve the most urgent organizations
    first, then the ones whose deadline is soonest, then the nearest. Sorting by
    that key and filling in order is exactly that rule. Nothing is traded off
    numerically, so an exhaustive search would give the same answer.
  * It is O(N log N) time and O(N) space for N candidate needs, which is
    effectively constant after the prefilter.

Stretch goal: this can be written as a small linear program (scipy.optimize.linprog)
that maximizes sum(weight_i * x_i) subject to sum(x_i) <= meals and
0 <= x_i <= remaining_i, where weight_i encodes priority, deadline and distance.
That becomes useful once weights are traded off against each other, for example
when splitting across several rescues at once.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

MAX_STOPS = 3

PRIORITY_RANK = {"HIGH": 2, "MEDIUM": 1, "LOW": 0}


def _get(obj: Any, key: str, default: Any = None) -> Any:
    """Read a field from a dict or an object (ORM row, dataclass, pydantic model)."""
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


def _deadline_ts(value: Any) -> float:
    """Deadline as a UNIX timestamp. Missing or unparseable deadlines sort last."""
    if value is None or value == "":
        return math.inf
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return math.inf
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.timestamp()


def remaining_meals(need: Any) -> int:
    """Meals a need still requires: meals_needed minus meals_fulfilled, never negative."""
    needed = int(_get(need, "meals_needed", 0) or 0)
    fulfilled = int(_get(need, "meals_fulfilled", 0) or 0)
    return max(needed - fulfilled, 0)


def rank_key(need: Any) -> tuple:
    """Sort key: priority descending, deadline ascending, distance ascending.

    distance_miles is optional. Logistics fills it in (restaurant to organization)
    when it has it; otherwise distance does not affect the order.
    """
    priority = PRIORITY_RANK.get(str(_get(need, "priority", "LOW")).upper(), 0)
    distance = _get(need, "distance_miles")
    distance = math.inf if distance is None else float(distance)
    return (-priority, _deadline_ts(_get(need, "deadline")), distance)


def allocate(meals: int, candidate_needs: Iterable[Any], max_stops: int = MAX_STOPS) -> List[Dict[str, int]]:
    """Split `meals` across `candidate_needs` and return [{need_id, meals}, ...].

    Each need is a dict or object with id, meals_needed, meals_fulfilled, priority,
    deadline, and optionally distance_miles. Needs are filled in rank order without
    going over any need's remaining meals, and at most `max_stops` needs are used.
    Meals left over after every chosen need is full go to the best ranked need,
    so food is never stranded at the restaurant. The result is ordered by rank.
    Logistics decides the driving order of the stops.
    """
    meals = int(meals)
    if meals <= 0:
        return []

    ranked = sorted(candidate_needs, key=rank_key)
    if not ranked:
        return []

    allocations: List[Dict[str, int]] = []
    left = meals
    for need in ranked:
        if left == 0 or len(allocations) == max_stops:
            break
        room = remaining_meals(need)
        if room == 0:
            continue
        give = min(left, room)
        allocations.append({"need_id": _get(need, "id"), "meals": give})
        left -= give

    if left > 0:
        best: Optional[Dict[str, int]] = allocations[0] if allocations else None
        if best is None:
            allocations.append({"need_id": _get(ranked[0], "id"), "meals": left})
        else:
            best["meals"] += left

    return allocations


def demand_fit(meals: int, allocations: List[Dict[str, int]], candidate_needs: Iterable[Any]) -> float:
    """Share of the rescue that went to real, unmet need (0 to 1).

    Meals pushed onto a need as leftover beyond its remaining meals do not count.
    Logistics can use this for the demand_fit term in its score.
    """
    if meals <= 0:
        return 0.0
    room = {_get(n, "id"): remaining_meals(n) for n in candidate_needs}
    placed = sum(min(a["meals"], room.get(a["need_id"], 0)) for a in allocations)
    return min(placed / meals, 1.0)
