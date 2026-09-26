# Autonomous delivery in FoodFlow (simulated)

**Nothing here uses a Waymo API.** FoodFlow has no Waymo or robot integration. `SimulatedWaymoProvider` and
`SimulatedSidewalkRobotProvider` model the constraints a curbside fleet would face, and every quote, trip and
audit event they produce carries `simulated: true`. Travel times come from open data: an ETA model trained on
OSRM road-network times over OpenStreetMap (see [../DATA_SOURCES.md](../DATA_SOURCES.md)).

## Why late night

Surplus appears at closing, often after 10 PM, when volunteer availability is lowest (in the fictional seed, four
of six volunteers are unavailable after 10 PM). A vehicle that runs at midnight could close that gap, but only where
someone can hand food over at a curb on both ends.

## Modeled constraints

| Constraint | How it is enforced | Test |
|---|---|---|
| Service area | Pickup and drop off must be inside a GeoJSON geofence (`backend/data/av_zone_illustrative.geojson`), labeled "illustrative demo zone", not an official service area | `test_av_never_chosen_when_restaurant_unstaffed_or_outside_zone`, `test_robot_constraints` |
| Curbside only | Restaurant must be staffed at the pickup ETA plus the load window; the org must have said (Q1) staff can meet a vehicle | `test_av_never_chosen_when_restaurant_unstaffed_or_outside_zone`, `test_no_av_dropoff_where_curbside_is_false` |
| Load/unload window | `LOAD_WINDOW_MIN` (5); a missed load window sends the vehicle away and hands the rescue to volunteers | `test_missed_load_window_falls_back_to_a_volunteer` |
| Point to point | One pickup and one drop off per vehicle trip; a split allocation becomes several vehicle trips or one volunteer multi-stop trip, whichever scores lower | `test_split_allocation_becomes_point_to_point_av_trips` |
| Cargo | Vehicle capacity per type; hot/cold/frozen food needs insulated totes (tracked per restaurant, returned later) | `test_robot_constraints` |
| Sidewalk robots | Distance and quantity limits, curbside both ends | `test_robot_constraints` |

Tests are in `backend/tests/test_fleet.py`.

## Mode selection

For each delivery leg: feasibility first, then a score in minute-equivalents: minutes to arrival + a penalty for
arriving with less than 60 minutes before safe_until + (1 - reliability) x 60 + staff handoff minutes. Reliability
is the observed completion rate per mode, blended with a prior (an assumption). Each trip stores a plain-English
`mode_reason`, for example from a real run:

> Simulated Waymo selected (simulated, no real vehicle): posted 11:40 PM, no volunteer can take it (4 not available
> at this hour, 2 without the right cooler or bags), both sites in the illustrative service zone, Demo Community
> Fridge open 24 hours with curbside staff.

## Handoff

`vehicle_arriving -> at_pickup_curb (load timer) -> loading -> loaded -> in_transit -> at_dropoff_curb (unload timer)
-> unloaded -> received`. Restaurant staff unlock with their pickup code, load and confirm the item count; the org
unlocks with its drop-off code, unloads and confirms receipt.

## Fleet comparison (from a real run)

`GET /analytics/compare-fleets` runs the same seeded fictional Friday (5 PM to 3 AM, 14 posts, 6 of them between
10 PM and 1 AM) twice through the real posting, matching, handoff and failure code, in an isolated in-memory
database with a fake clock. Simulated people follow fixed rules with a 10% seeded volunteer no-show rate. Output of
the run committed as [compare-fleets-run.json](compare-fleets-run.json):

| | Volunteer only | Mixed fleet (simulated AVs) |
|---|---|---|
| Meals posted | 340 | 340 |
| Meals delivered | 90 | 120 |
| Meals expired | 98 | 98 |
| Meals not delivered by 3 AM (other) | 152 | 122 |
| Median minutes, post to receipt | 20.0 | 20.5 |
| Late night (10 PM to 1 AM): posted / delivered / expired | 196 / 0 / 64 | 196 / 30 / 64 |
| Delivered by mode | volunteer 90 | volunteer 90, waymo_sim 30 |

What the numbers show:

- The simulated vehicles delivered 30 late-night meals that volunteers could not (all volunteers were unavailable
  or lacked equipment at that hour). Evening results were identical.
- The mixed fleet did **not** reduce expired meals (98 in both).
- Most undelivered food was limited by receivers, not carriers. Inspecting the undelivered rescues in the mixed
  run, every one had no eligible organization: open orgs had already met their nightly need, others were closed,
  or dietary rules excluded them. More vehicles do not fix that; more receiving capacity late at night would.

These are simulation results on fictional data, not a forecast of real performance.

## What is real, simulated, or needs a partner

- Real: the matching, eligibility, handoff state machine, audit trail and failure handling code; open road data.
- Simulated: every vehicle and robot, their availability, capacity and timing; the people in the comparison.
- Needs a partner: any real autonomous vehicle integration and an official service area. FoodFlow would implement
  the same `FleetProvider` interface against a real API if one were ever provided.
