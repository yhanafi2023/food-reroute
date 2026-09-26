"""One-time import: real Census tract poverty data for the demo's Miami-Dade area.

  cd backend && .venv/bin/python -m scripts.import_census_tracts

Two Census Bureau sources, neither invented:
  * Tract polygons: TIGERweb REST (tigerweb.geo.census.gov), no API key needed.
  * Poverty stats: ACS 2024 5-Year Estimates, Table S1701 "Poverty Status in the
    Past 12 Months" (api.census.gov/data/2024/acs/acs5/subject), needs
    CENSUS_API_KEY (backend/.env; see .env.example) -- the Bureau requires a key
    for every api.census.gov/data query now, even unauthenticated historical
    vintages. Get one free and instantly at https://api.census.gov/data/key_signup.html.

Writes backend/data/census_tracts_miami_dade.json. The running app only ever
reads this file (see app/community_need.py) -- no network call at request time,
per the "reliability over repeated external calls" guidance for a hackathon demo.

Run this again whenever CENSUS_API_KEY changes or the demo's service area grows;
the file is checked into the repo like data/miami_prospects.json and
data/av_zone_illustrative.geojson.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import httpx
from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parents[1]
load_dotenv(BACKEND_DIR / ".env")

OUT_FILE = BACKEND_DIR / "data" / "census_tracts_miami_dade.json"
STATE_FIPS, COUNTY_FIPS = "12", "086"  # Florida, Miami-Dade County
SOURCE = "U.S. Census Bureau, 2024 ACS 5-Year Estimates (Table S1701, Poverty Status in the Past 12 Months)"

# Padded bounding box around every seeded restaurant, organization and volunteer
# home location in app/seed.py, so the choropleth covers the whole demo area
# plus its surroundings.
BBOX = {"min_lng": -80.44, "min_lat": 25.70, "max_lng": -80.29, "max_lat": 25.83}

TIGERWEB_URL = "https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/Tracts_Blocks/MapServer/0/query"
ACS_URL = "https://api.census.gov/data/2024/acs/acs5/subject"

MAX_RING_POINTS = 180  # decimate very detailed shoreline/water tracts; keeps the file small
MIN_RELIABLE_POPULATION = 50  # ACS estimates from a tiny population base are not meaningful (e.g. n=4 -> +/-100% MOE)


def bucket(poverty_rate: float) -> str:
    """Visualization-only bucket (not an official Census classification)."""
    if poverty_rate < 10:
        return "low"
    if poverty_rate < 20:
        return "moderate"
    if poverty_rate < 30:
        return "high"
    return "very_high"


def community_need_score(poverty_rate: float) -> float:
    """Normalize a tract poverty rate (percent) to [0, 1].

    Linear up to a 40% ceiling, then clamped. A ceiling (not a min-max rescale
    over whatever tracts happen to be loaded) keeps one unusually poor or
    unusually affluent tract from single-handedly stretching or compressing
    every other tract's score.
    """
    return max(0.0, min(1.0, poverty_rate / 40.0))


def fetch_tract_geometry() -> dict:
    params = {
        "geometry": f"{BBOX['min_lng']},{BBOX['min_lat']},{BBOX['max_lng']},{BBOX['max_lat']}",
        "geometryType": "esriGeometryEnvelope", "inSR": "4326", "outSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
        "where": f"STATE='{STATE_FIPS}' AND COUNTY='{COUNTY_FIPS}'",
        "outFields": "GEOID,TRACT,NAME", "f": "geojson",
    }
    r = httpx.get(TIGERWEB_URL, params=params, timeout=30)
    r.raise_for_status()
    doc = r.json()
    if "features" not in doc:
        raise RuntimeError(f"TIGERweb query failed: {doc}")
    return {f["properties"]["GEOID"]: f for f in doc["features"]}


def fetch_poverty_stats(key: str) -> dict:
    params = {
        "get": "NAME,S1701_C03_001E,S1701_C03_001M,S1701_C01_001E,S1701_C02_001E",
        "for": "tract:*", "in": f"state:{STATE_FIPS} county:{COUNTY_FIPS}", "key": key,
    }
    r = httpx.get(ACS_URL, params=params, timeout=30)
    r.raise_for_status()
    rows = r.json()
    header, body = rows[0], rows[1:]
    idx = {name: i for i, name in enumerate(header)}
    out = {}
    for row in body:
        geoid = row[idx["state"]] + row[idx["county"]] + row[idx["tract"]]
        # ACS marks a suppressed/inapplicable estimate as a large negative sentinel (-666666666).
        poverty_rate = float(row[idx["S1701_C03_001E"]])
        if poverty_rate < 0:
            continue
        out[geoid] = {
            "name": row[idx["NAME"]],
            "poverty_rate": round(poverty_rate, 1),
            "margin_of_error_pct": round(float(row[idx["S1701_C03_001M"]]), 1),
            "population": int(row[idx["S1701_C01_001E"]]),
            "population_below_poverty": int(row[idx["S1701_C02_001E"]]),
        }
    return out


def decimate(ring: list, max_points: int = MAX_RING_POINTS) -> list:
    if len(ring) <= max_points:
        return ring
    step = len(ring) / max_points
    kept = [ring[int(i * step)] for i in range(max_points)]
    if kept[-1] != ring[-1]:
        kept.append(ring[-1])  # keep polygons closed
    return kept


def simplify_geometry(geometry: dict) -> dict:
    coords = geometry["coordinates"]
    if geometry["type"] == "Polygon":
        rings = [[[round(x, 5), round(y, 5)] for x, y in decimate(ring)] for ring in coords]
    else:  # MultiPolygon
        rings = [[[[round(x, 5), round(y, 5)] for x, y in decimate(ring)] for ring in poly] for poly in coords]
    return {"type": geometry["type"], "coordinates": rings}


def main() -> None:
    key = os.getenv("CENSUS_API_KEY", "").strip()
    if not key:
        print("CENSUS_API_KEY is not set in backend/.env. Get a free key at "
              "https://api.census.gov/data/key_signup.html and set it, then re-run this script.",
              file=sys.stderr)
        raise SystemExit(1)

    print(f"Fetching tract geometry for state {STATE_FIPS} county {COUNTY_FIPS} within the demo bounding box...")
    geoms = fetch_tract_geometry()
    print(f"  {len(geoms)} tracts intersect the demo area.")

    print("Fetching ACS 2024 5-Year poverty statistics (table S1701)...")
    stats = fetch_poverty_stats(key)
    print(f"  {len(stats)} tracts have a poverty estimate for the county.")

    tracts = []
    missing = []
    unreliable = []
    for geoid, feature in geoms.items():
        s = stats.get(geoid)
        if s is None:
            missing.append(geoid)
            continue
        if s["population"] < MIN_RELIABLE_POPULATION:
            # A poverty rate computed from a tiny population base (e.g. a park, airport, or other
            # non-residential sliver clipped by the bounding box) is statistically meaningless --
            # real Census output, but not a community, so it is left out of the demo layer.
            unreliable.append((geoid, s["population"]))
            continue
        tracts.append({
            "geoid": geoid,
            "name": s["name"],
            "poverty_rate": s["poverty_rate"],
            "margin_of_error_pct": s["margin_of_error_pct"],
            "population": s["population"],
            "population_below_poverty": s["population_below_poverty"],
            "bucket": bucket(s["poverty_rate"]),
            "community_need_score": round(community_need_score(s["poverty_rate"]), 4),
            "geometry": simplify_geometry(feature["geometry"]),
        })
    if missing:
        print(f"  {len(missing)} tracts in the bounding box had no ACS estimate (likely water/park-only "
              f"tracts with no population) and were skipped: {missing[:5]}{'...' if len(missing) > 5 else ''}")
    if unreliable:
        print(f"  {len(unreliable)} tracts had a population base under {MIN_RELIABLE_POPULATION} "
              f"(statistically unreliable) and were skipped: {unreliable}")

    payload = {
        "source": SOURCE,
        "fetched_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "state_fips": STATE_FIPS, "county_fips": COUNTY_FIPS, "bbox": BBOX,
        "bucket_note": "Low/Moderate/High/Very High are FoodFlow visualization buckets for this demo, "
                       "not official Census classifications.",
        "tract_count": len(tracts),
        "tracts": tracts,
    }
    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(json.dumps(payload, indent=1))
    print(f"Wrote {len(tracts)} tracts to {OUT_FILE}")


if __name__ == "__main__":
    main()
