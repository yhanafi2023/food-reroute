"""FleetProvider interface (section 6a). Every provider answers the same five questions."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional, Protocol, Tuple

Point = Tuple[float, float]


@dataclass
class Cargo:
    meals: int
    totes_available: int = 0


@dataclass
class Quote:
    feasible: bool
    mode: str
    simulated: bool
    eta_pickup: Optional[datetime] = None
    eta_dropoff: Optional[datetime] = None
    reason: str = ""
    estimated: bool = False
    carrier_id: Optional[Any] = None
    totes_needed: int = 0
    extra: Dict[str, Any] = field(default_factory=dict)

    def as_json(self) -> Dict[str, Any]:
        d = asdict(self)
        for k in ("eta_pickup", "eta_dropoff"):
            d[k] = d[k].isoformat() + "Z" if d[k] else None
        return d


class FleetProvider(Protocol):
    mode: str
    simulated: bool

    def availability(self, zone: str, window: Tuple[datetime, datetime]) -> Dict[str, Any]: ...
    def quote(self, pickup: Point, dropoff: Point, cargo: Cargo, start_at: datetime) -> Quote: ...
    def dispatch(self, trip) -> str: ...
    def status(self, vehicle_id: str) -> Dict[str, Any]: ...
    def cancel(self, trip) -> None: ...
