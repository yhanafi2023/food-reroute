"""Split one food rescue across the community organizations that need it.

Ranking is a small weighted score (app.assumptions.MATCHING_WEIGHTS), not a pure
lexicographic sort -- this is the "stretch goal" the module used to describe as
future work: sum(weight_i * component_i) over normalized [0, 1] components,
maximized subject to sum(x_i) <= meals and 0 <= x_i <= remaining_i. It stays a
fill-in-rank-order greedy pass rather than a linear program because:
  * The logistics prefilter hands us at most ~5 candidate needs, and a single
    driver trip carries at most MAX_STOPS drop offs, so the search space is
    tiny; an exhaustive search over so few candidates gives the same answer.
  * It is O(N log N) time and O(N) space for N candidate needs, effectively
    constant after the prefilter.

Components (each normalized to [0, 1], higher is always better):
  distance_score       nearer to MATCH_RADIUS_MI scores higher
  urgency_score        this organization's own receiving window closing soon
                       scores higher (send it there before the option disappears)
  demand_score         share of the rescue this organization alone could
                       usefully absorb (avoids stranding food on one small need)
  capacity_score       operational headroom beyond just this rescue -- distinct
                       from demand_score: an org that could take 3x this rescue
                       scores higher here than one that can only just fit it,
                       even when both look identical on demand_score
  community_need_score Census-tract poverty rate where the organization is
                       located (app.community_need), 0.0 when no tract match
                       exists for that point -- never a hard requirement

This never overrides a hard constraint: app.eligibility.check has already
removed anything infeasible (capacity <= 0, closed, wrong food category, past
safe_until, ...) before any of these candidates are scored. Community need is
one optimization factor among feasible matches, expressing "given limited
surplus food, where can it do meaningful good while remaining operationally
feasible" -- never a claim about the relative worth of the people in an area.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

from app import community_need
from app.assumptions import MATCH_RADIUS_MI, MATCHING_WEIGHTS

MAX_STOPS = 3
URGENCY_HORIZON_MINUTES = 180.0

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


def _priority_rank(need: Any) -> int:
    return PRIORITY_RANK.get(str(_get(need, "priority", "LOW")).upper(), 0)


def score_need(need: Any, meals: int, now: Optional[datetime] = None,
              weights: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
    """Named, normalized [0, 1] component scores for ranking one candidate organization
    (`need`) against one rescue of `meals` meals. See the module docstring for what
    each component means. `weights` defaults to app.assumptions.MATCHING_WEIGHTS;
    pass MATCHING_WEIGHTS_COMMUNITY_PRIORITY for the "what if" comparison.
    """
    w = weights or MATCHING_WEIGHTS
    now = now or datetime.now(timezone.utc)

    distance = _get(need, "distance_miles")
    distance_score = 0.5 if distance is None else max(0.0, min(1.0, 1 - float(distance) / MATCH_RADIUS_MI))

    deadline_ts = _deadline_ts(_get(need, "deadline"))
    if math.isinf(deadline_ts):
        urgency_score = 0.0  # no closing-window signal for this organization: neutral, not urgent
    else:
        minutes_left = (deadline_ts - now.timestamp()) / 60.0
        urgency_score = max(0.0, min(1.0, 1 - minutes_left / URGENCY_HORIZON_MINUTES))

    room = remaining_meals(need)
    demand_score = 0.0 if meals <= 0 else max(0.0, min(1.0, min(room, meals) / meals))
    # Headroom beyond just this rescue, saturating at 2x rather than demand_score's 1x --
    # deliberately a different number from demand_score (an org that could take double this
    # rescue scores higher here than one that can only just fit it, even when both look
    # identical on demand_score).
    capacity_score = 0.0 if meals <= 0 else max(0.0, min(1.0, room / (2 * meals)))

    lat, lng = _get(need, "lat"), _get(need, "lng")
    need_info = community_need.score_for(lat, lng) if lat is not None and lng is not None else None
    need_score = need_info["community_need_score"] if need_info else 0.0

    components = {"distance_score": round(distance_score, 4), "urgency_score": round(urgency_score, 4),
                 "demand_score": round(demand_score, 4), "capacity_score": round(capacity_score, 4),
                 "community_need_score": round(need_score, 4)}
    total = sum(w[key[: -len("_score")]] * value for key, value in components.items())
    return {**components, "total": round(total, 4), "community_need": need_info}


SCORE_COMPONENT_KEYS = ("distance_score", "urgency_score", "demand_score", "capacity_score", "community_need_score")


def reweight_total(components: Dict[str, float], weights: Dict[str, float]) -> float:
    """Recompute a weighted total from already-normalized component scores under a
    different weight preset, without needing the original raw candidate data again.
    Used for the read-only "what if we prioritized community impact?" comparison."""
    return round(sum(weights[key[: -len("_score")]] * components[key] for key in SCORE_COMPONENT_KEYS), 4)


def rank_candidates(candidate_needs: Iterable[Any], meals: int, now: Optional[datetime] = None,
                    weights: Optional[Dict[str, float]] = None) -> List[Dict[str, Any]]:
    """Every candidate scored and sorted best first.

    Priority stays a pre-sort tier (HIGH before MEDIUM before LOW) for backward
    compatibility with logistics/matching.py's priority-based demo plans; within
    a tier (in the real dispatcher every organization is MEDIUM today, so this is
    the whole ranking) the weighted score decides. Returns [{need, score}, ...].
    """
    scored = [{"need": n, "score": score_need(n, meals, now, weights)} for n in candidate_needs]
    scored.sort(key=lambda s: (-_priority_rank(s["need"]), -s["score"]["total"]))
    return scored


def allocate(meals: int, candidate_needs: Iterable[Any], max_stops: int = MAX_STOPS,
            now: Optional[datetime] = None, weights: Optional[Dict[str, float]] = None) -> List[Dict[str, int]]:
    """Split `meals` across `candidate_needs` and return [{need_id, meals}, ...].

    Each need is a dict or object with id, meals_needed, meals_fulfilled, priority,
    deadline, and optionally distance_miles, lat, lng. Needs are filled in rank
    order (see rank_candidates) without going over any need's remaining meals, and
    at most `max_stops` needs are used. Meals left over after every chosen need is
    full go to the best ranked need, so food is never stranded at the restaurant.
    The result is ordered by rank. Logistics decides the driving order of stops.
    """
    meals = int(meals)
    if meals <= 0:
        return []

    ranked = [s["need"] for s in rank_candidates(candidate_needs, meals, now, weights)]
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
