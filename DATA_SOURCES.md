# FoodFlow data sources

What FoodFlow shows, where each piece comes from, and how much to trust it. Checked 2026-09-26.
Focus area: Miami-Dade County, centered on FIU Modesto A. Maidique Campus (11200 SW 8th St).

## At a glance

| What | Status | Source |
|---|---|---|
| Miami prospect directory (14 businesses) | **Verified public data** | Business websites, a food-rescue organization's donor list, surplus-marketplace listings, U.S. Census geocoder |
| Map pins for prospects | **Verified public data** | U.S. Census Bureau Geocoder (Public_AR_Current) |
| Driver ETA model | **Real road-network data** (not observed trips) | 27,172 OSRM car-profile travel times over OpenStreetMap roads, fetched 2026-09-26 |
| Road routes on the map | **Real road-network data** | OSRM (or Mapbox Directions when a token is set); straight-line fallback labeled "offline" |
| Handling time per stop (6 min) | **Assumption** | Not measured; stated wherever ETAs appear |
| Meal value (MEAL_VALUE_USD, default 3.0) | **Assumption** | Placeholder; replace with a sourced figure |
| Seven-day surplus logs | **Self-reported by businesses** | Entered by the business (or by staff from what the business reports) |
| Demo restaurants, drivers, organizations | **Fictional** | Demo accounts for clicking through the flow; labeled "fictional demo" in the UI; addresses read "Demo location near FIU" |
| Seeded past deliveries (87 meals) | **Fictional** | Excluded from the public impact page |
| Simulate Tonight | **Simulated** | Runs the real matching and ETA code over the fictional demo network with a fixed seed; labeled "simulated" |
| Surplus forecast model | **Synthetic training data: not served** | The model in `backend/app/intelligence/ml` is trained on generated data, so the API returns "not available" until 90 real logged days exist |
| Public impact page | **Real only** | Counts only deliveries confirmed by a receiving organization from non-demo restaurants (currently 0) |

## Miami prospect directory

File: [`backend/data/miami_prospects.json`](backend/data/miami_prospects.json). Every record lists its sources, the
date checked, and how each source was checked ("page read" means we read the page; "search index only" means the
page title appeared in search results but the page itself could not be read).

These are **prospects, not partners**. No record says a business discards food. Evidence levels:

- **measured**: a business-specific surplus quantity with a reporting period. *None found for any business.*
- **documented_donation**: a food-rescue organization publicly names the business as a donor. Found for Macchialina
  (Food Rescue US - South Florida's Give Miami Day profile: "restaurants like MILA, Papi Steak, Macchialina and CHŌ";
  no date, quantity or frequency given).
- **marketplace_listing**: a Too Good To Go listing appears in search results. The listing pages sit behind a bot
  checkpoint, so their contents, prices and current availability were **not** verified. A listing shows a business
  has offered surplus for resale; it does not show quantities, and resale food is not available for donation.
- **none_found**: identity and address verified on the business's own site; no surplus evidence found. Included as
  high-volume kitchens near FIU to invite into the seven-day log.

| Business | Neighborhood | Evidence | Address source |
|---|---|---|---|
| Sergio's (FIU location) | FIU campus | none found | sergios.com (published "1200 SW 8th Street, 33199", likely a typo for 11200; pinned at FIU) |
| MIA Bakery Gourmet | Doral | marketplace listing | Toast ordering page title (page returned 403) |
| Smoothie Spot (Tamiami) | Tamiami | marketplace listing | smoothiespotmiami.com |
| Sergio's Restaurant (Bird Road) | Westchester | none found | sergios.com |
| Cuban Guys (W Flagler) | Fontainebleau / West Flagler | none found | cubanguysrestaurants.com |
| Karla Cuban Bakery (Westchester) | Westchester | marketplace listing | karlabakery.com |
| Karla Cuban Bakery (Doral) | Doral | marketplace listing | karlabakery.com |
| Bodeguita Mercado Cafetería | Coral Way / Coral Terrace | marketplace listing | third-party listings (Uber Eats, Waze) |
| Cuban Guys (Kendall) | Kendall | none found | cubanguysrestaurants.com |
| Sergio's Restaurant (Kendall 107th) | Kendall | none found | sergios.com |
| Manhattan Chicago Pizza (Kendall) | Kendall | marketplace listing | third-party listings (official site shows phone only) |
| Dolce Saturno Bakery (Doral) | Doral | marketplace listing | dolcesaturno.com |
| Versailles Restaurant | Little Havana | none found | versaillesrestaurant.com |
| Macchialina | Miami Beach | documented donation | macchialina.com says **820** Alton Road; Michelin, Toast and the visitor bureau say 810 |

Neighborhood labels were assigned by FoodFlow from the address; they are not official boundaries.

**Ranking.** A business is ranked only with measured recoverable surplus (safe food that would be thrown away or
composted), pickup frequency (days per week with recoverable surplus), and existing commitments (a business already
served by a donation or resale program ranks after those that are not). Today no business qualifies, so the ranking
is empty and the directory offers the seven-day log instead.

## Driver ETA model

- Data: [`backend/data/eta_osrm_miami.csv`](backend/data/eta_osrm_miami.csv) (27,172 ordered pairs) with
  [`eta_osrm_miami.meta.json`](backend/data/eta_osrm_miami.meta.json). Fetched by
  `python -m app.intelligence.eta.fetch_osrm` from the public OSRM server (`router.project-osrm.org`, car profile).
  Points: FIU, the 14 prospect locations, and seeded random sample points across western Miami-Dade and Miami Beach,
  each snapped to the nearest road (points more than 300 m from a road dropped). Map data © OpenStreetMap
  contributors (ODbL).
- Model: HistGradientBoosting (P50, absolute error) chosen over Ridge and the old 22 mph rule; P10 and P90 from
  quantile models widened by conformal calibration.
- Results on held-out sample points: average error **2.8 min** (old rule 10.0, Ridge 4.7; average trip 21.1 min).
  P10 to P90 range held 76% of trips (target 80%; 45% before calibration).
- Limits: OSRM times are free-flow road-network estimates, **not observed trips and no traffic**. Real FoodFlow trip
  legs are logged (`trip_legs`) and the admin can retrain with them (legs of 2 to 180 minutes).

## Driver position on the map

- **Live GPS** when the driver turns on "Share live location" (sent at most every 10 s).
- Otherwise **estimated**: placed along the real route leg by elapsed time over the model's P50, and labeled
  "estimated position". It never claims arrival; the driver confirms each stop.

## What needs a partner integration

| Need | Why | Integration |
|---|---|---|
| Measured surplus quantities | No business publishes them | Seven-day log now; POS or waste-tracking integration later |
| Live traffic in ETAs | OSRM has none | Mapbox `driving-traffic` (token) or retraining on logged real trips |
| Surplus forecast | Needs real history | Train on real logs once ≥ 90 logged days exist |
| Too Good To Go listing details | Pages blocked to automated readers | Ask the business, or a data-sharing agreement |
| Real partner relationships | None exist yet | Outreach; every researched business is "not enrolled" |
| Meal value per meal | Placeholder | A sourced figure (e.g. from a food bank's published methodology) |
