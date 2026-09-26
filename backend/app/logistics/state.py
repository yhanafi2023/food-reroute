"""Delivery status state machine. Statuses only move forward one step at a time."""
from __future__ import annotations

from typing import Optional

DELIVERY_FLOW = [
    "HEADING_TO_RESTAURANT",
    "ARRIVED_AT_RESTAURANT",
    "PICKED_UP",
    "DELIVERING",
    "DELIVERED",
    "CONFIRMED",
]

# Rescue status that each delivery status implies.
RESCUE_STATUS_FOR_DELIVERY = {
    "HEADING_TO_RESTAURANT": "ACCEPTED",
    "ARRIVED_AT_RESTAURANT": "ACCEPTED",
    "PICKED_UP": "PICKED_UP",
    "DELIVERING": "PICKED_UP",
    "DELIVERED": "DELIVERED",
    "CONFIRMED": "CONFIRMED",
}


def next_status(current: str, requested: str) -> str:
    """Return `requested` if it is the single legal next step after `current`.

    Raises ValueError for unknown statuses, skipped steps, repeats, or going back.
    """
    if requested not in DELIVERY_FLOW:
        raise ValueError(f"Unknown delivery status {requested!r}")
    if current not in DELIVERY_FLOW:
        raise ValueError(f"Unknown delivery status {current!r}")
    expected = following_status(current)
    if requested != expected:
        if expected is None:
            raise ValueError(f"Delivery is already {current}; no further status changes")
        raise ValueError(f"Cannot go from {current} to {requested}; the next step is {expected}")
    return requested


def following_status(current: str) -> Optional[str]:
    i = DELIVERY_FLOW.index(current)
    return DELIVERY_FLOW[i + 1] if i + 1 < len(DELIVERY_FLOW) else None
