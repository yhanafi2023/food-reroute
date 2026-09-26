"""Fetch REAL road-network travel times for Miami-Dade from the public OSRM server.

  python -m app.intelligence.eta.fetch_osrm      (from backend/, needs internet)

Points: FIU, the researched prospect locations (data/miami_prospects.json), and
sample points on a seeded random grid across western Miami-Dade and Miami Beach.
Each point is snapped to the nearest road by OSRM; points more than 300 m from a
road are dropped. For every ordered pair OSRM's table service returns the driving
duration and distance over OpenStreetMap roads.

What this is: real road-network times from OSRM's car profile (free-flow speeds
from road types and speed limits in OpenStreetMap).
What it is not: observed trips, and it has no live or historical traffic.

Output: data/eta_osrm_miami.csv and data/eta_osrm_miami.meta.json.
Map data (c) OpenStreetMap contributors, ODbL. Routing by OSRM (project-osrm.org).
"""
from __future__ import annotations

import csv
import json
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx
import numpy as np

OSRM = "https://router.project-osrm.org"
DATA = Path(__file__).resolve().parents[3] / "data"
BATCHES = 3
POINTS_PER_BATCH = 100
MAX_SNAP_METERS = 300
SEED = 11


def _anchor_points():
    doc = json.loads((DATA / "miami_prospects.json").read_text())
    pts = [(doc["reference_point"]["lat"], doc["reference_point"]["lng"])]
    pts += [(p["lat"], p["lng"]) for p in doc["prospects"]]
    return pts


def _grid(rng, n):
    lat = rng.uniform(25.66, 25.87, n)
    lng = rng.uniform(-80.45, -80.25, n)
    beach = rng.random(n) < 0.08
    lat = np.where(beach, rng.uniform(25.77, 25.84, n), lat)
    lng = np.where(beach, rng.uniform(-80.15, -80.125, n), lng)
    return list(zip(lat.round(6), lng.round(6)))


def fetch() -> None:
    rng = np.random.default_rng(SEED)
    anchors = _anchor_points()
    rows, requests = [], []
    for b in range(BATCHES):
        pts = anchors + _grid(rng, POINTS_PER_BATCH - len(anchors))
        coords = ";".join(f"{lng},{lat}" for lat, lng in pts)
        url = f"{OSRM}/table/v1/driving/{coords}"
        r = httpx.get(url, params={"annotations": "duration,distance"}, timeout=90)
        r.raise_for_status()
        d = r.json()
        if d.get("code") != "Ok":
            raise RuntimeError(d)
        requests.append({"batch": b, "points": len(pts), "fetched_at": datetime.now(timezone.utc).isoformat(timespec="seconds")})
        src = d["sources"]
        ok = [s["distance"] <= MAX_SNAP_METERS for s in src]
        for i, si in enumerate(src):
            for j, dj in enumerate(src):
                if i == j or not ok[i] or not ok[j]:
                    continue
                dur, dist = d["durations"][i][j], d["distances"][i][j]
                if dur is None or dist is None or dist < 200:
                    continue
                rows.append({
                    "start_lat": si["location"][1], "start_lng": si["location"][0],
                    "end_lat": dj["location"][1], "end_lng": dj["location"][0],
                    "osrm_minutes": round(dur / 60.0, 3), "osrm_miles": round(dist / 1609.344, 4), "batch": b,
                })
        time.sleep(2)  # be polite to the public demo server

    DATA.mkdir(exist_ok=True)
    with open(DATA / "eta_osrm_miami.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)
    meta = {
        "source": "OSRM table service, car profile, public demo server",
        "server": OSRM,
        "map_data": "OpenStreetMap contributors (ODbL)",
        "fetched": datetime.now(timezone.utc).date().isoformat(),
        "requests": requests,
        "pairs": len(rows),
        "snap_limit_meters": MAX_SNAP_METERS,
        "anchors": "FIU campus address and the researched prospect locations in miami_prospects.json",
        "sample_points": f"seeded (seed {SEED}) random points in lat 25.66-25.87, lng -80.45 to -80.25, plus Miami Beach",
        "limitations": "Free-flow road-network times; no live or historical traffic; not observed trips.",
    }
    (DATA / "eta_osrm_miami.meta.json").write_text(json.dumps(meta, indent=1))
    print(f"Saved {len(rows)} real OSRM pairs")


if __name__ == "__main__":
    fetch()
