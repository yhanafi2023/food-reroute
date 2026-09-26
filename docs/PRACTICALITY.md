# Practicality: could real people use this?

Designed for real conditions: a cook at closing time with 30 seconds and greasy hands, a volunteer with bad
signal, a shelter coordinator who needs numbers for grant reports, a vehicle that cannot carry food to the door.
Every rule below is enforced in the backend (database constraints or API checks), not only in a UI.

All accounts and organizations in the demo are fictional. No user research was done yet; see
[ORG_RESEARCH.md](ORG_RESEARCH.md) for the interview template.

## Persona walkthroughs (measured)

Measured by running `backend/scripts/walkthroughs.py` (FastAPI test client, fictional seed, Friday 7 PM Miami).
The counts are the API calls a client app makes; sign-in is two calls (request code, verify).

### Restaurant staff: 4 API calls

| # | Step | Call | Status |
|---|---|---|---|
| 1 | sign in | `POST /auth/request-code` | 200 |
| 2 | sign in | `POST /auth/verify` | 200 |
| 3 | quick post (quantity, unit, category, deadline + attestation) | `POST /rescues` | 200 |
| 4 | open the rescue to read the pickup code | `GET /rescues/{id}` | 200 |

The post returns the match immediately (carrier, ETA, pickup code), so step 4 is only needed later at handoff.
"Repeat last post" (`POST /rescues/repeat-last`) and one-tap recurring drafts (`POST /rescues/{id}/confirm`)
make a regular night's post one call after sign-in.

### Volunteer: 6 API calls

| # | Step | Call | Status |
|---|---|---|---|
| 1 | sign in | `POST /auth/request-code` | 200 |
| 2 | sign in | `POST /auth/verify` | 200 |
| 3 | see the offer | `GET /volunteers/me/trips` | 200 |
| 4 | accept | `POST /trips/{id}/accept` | 200 |
| 5 | enter pickup code and meal count | `POST /trips/{id}/pickup` | 200 |
| 6 | enter drop-off code | `POST /stops/{id}/deliver` | 200 |

Steps 4 to 6 accept an `Idempotency-Key` header: a retried tap on a bad connection replays the first response
instead of applying twice.

### Organization coordinator: 8 API calls

| # | Step | Call | Status |
|---|---|---|---|
| 1 | sign in | `POST /auth/request-code` | 200 |
| 2 | sign in | `POST /auth/verify` | 200 |
| 3 | see incoming and to-confirm deliveries | `GET /orgs/me/deliveries` | 200 |
| 4 | confirm receipt (condition, temperature, name) | `POST /stops/{id}/receipt` | 200 |
| 5 | open the donor acknowledgment | `GET /acknowledgments` | 200 |
| 6 | e-sign it | `POST /acknowledgments/{id}/sign` | 200 |
| 7 | build this month's report | `POST /orgs/me/reports` | 200 |
| 8 | download the CSV | `GET /orgs/me/reports/{id}/download` | 200 |

Reports are also generated automatically at each org's chosen frequency, so steps 7 and 8 become one download.

## What happens when things go wrong

| Scenario | What the system does | Test that proves it |
|---|---|---|
| Volunteer does not show up | After `NO_SHOW_GRACE_MIN` past the expected pickup, the trip is reassigned, that volunteer is excluded, the rescue re-queues and the restaurant is notified | `tests/test_failures.py::test_volunteer_no_show_requeues_and_notifies_restaurant` |
| Volunteer declines or cancels before pickup | Trip reassigned, volunteer excluded, re-matched | `app/routes/trips.py` decline/cancel; `tests/test_lifecycle.py::test_illegal_transitions_return_409` (cancel after pickup refused) |
| Food passes safe_until before pickup | Scheduled job expires it, closes trips, notifies restaurant, carrier and orgs, logs it; checked before no-shows so expired food is never re-queued | `tests/test_failures.py::test_food_past_safe_until_expires_and_everyone_is_told` |
| Org closed or full on arrival | Carrier reports it; meals re-routed through allocation to the next eligible org; carrier and new org notified | `tests/test_failures.py::test_org_closed_on_arrival_reroutes_to_next_eligible_org` |
| Org refuses before arrival | Same re-route | `tests/test_failures.py::test_org_refuses_before_arrival` |
| Org schedule changed after pickup | Scheduler sees the drop off would now arrive while closed and re-routes | `tests/test_failures.py::test_schedule_change_after_pickup_reroutes_automatically` |
| Restaurant cancels after matching | Trip closed, carrier and orgs notified | `tests/test_failures.py::test_restaurant_cancel_after_match_closes_trip_and_notifies_carrier` |
| Simulated AV load window missed | Vehicle leaves, rescue re-queues for volunteers only, a volunteer takes over | `tests/test_fleet.py::test_missed_load_window_falls_back_to_a_volunteer` |
| Routing or allocation service down | Haversine x 1.3 at 30 km/h and nearest eligible org; responses flagged `estimated: true` | `tests/test_failures.py::test_routing_and_allocation_services_down_fall_back_with_estimated_flag` |
| Retried request on bad signal | `Idempotency-Key` replays the stored response; reuse for a different request is 422 | `tests/test_lifecycle.py::test_idempotent_retry_does_not_double_apply` |
| Illegal state change | 409 with a plain-English message | `tests/test_lifecycle.py::test_every_transition_in_the_state_machine` |
| Wrong pickup or drop-off code | 400, and the failed attempt stays in the audit log | `tests/test_lifecycle.py::test_full_handoff_with_codes_quantities_receipt_and_audit` |
| Double post from a busy kitchen | Near-identical post within 10 minutes is linked with a warning | `tests/test_posting.py::test_duplicate_warning_within_ten_minutes` |
| Org has not finished onboarding | Receives no deliveries; explanation says so | `tests/test_matching.py::test_incomplete_org_receives_nothing` |
| Someone edits the audit log | Database trigger refuses UPDATE and DELETE | `tests/test_lifecycle.py::test_audit_log_is_append_only` |
| A notification provider fails | The request still succeeds; the outbox records the failure | `tests/test_notifications.py::test_a_failing_provider_never_breaks_the_request` |

## Permissions (server-side)

Restaurants see only their own posts; volunteers see their offers and trips; orgs see only drop offs addressed to
them (and only their own drop-off code); admins see everything. Others' objects return 404. Restaurants and orgs
see a volunteer's first name, vehicle and a masked phone (`***-***-1234`), never the full number or home location.
Tests: `tests/test_lifecycle.py::test_restaurants_see_only_their_posts_and_others_get_404`,
`tests/test_lifecycle.py::test_quick_post_matches_a_volunteer_and_shows_codes_only_to_the_right_people`,
`tests/test_accounts.py::test_role_boundaries_on_admin_and_profiles`.

## Assumptions

All served at `GET /config/assumptions` and set in `backend/app/assumptions.py`.

| Assumption | Value | Basis |
|---|---|---|
| Meals per unit | individual meal 1, bag 4, box 8, tray 12, half pan 10, full pan 20 | FoodFlow planning values; replace with each restaurant's counts |
| safe_until after preparation | hot 2 h, cold 4 h, frozen 4 h, shelf-stable 48 h | Hot follows USDA FSIS guidance (no more than 2 hours out, 1 hour above 90 F); others are planning values |
| Pounds per meal | 1.2 | Feeding America ("Each meal is roughly 1.2 pounds") |
| No-show grace period | 15 min past expected pickup | Assumption |
| Duplicate window | 10 min | Build spec |
| Intake confirmation | every 90 days | Build spec |
| Handling time per stop | 6 min | Assumption (ETA model) |
| Loading time at pickup | 5 min | Assumption |
| Vehicle load/unload window | 5 min | Assumption (`LOAD_WINDOW_MIN`) |
| Simulated AV capacity, fleet size, dispatch delay | 60 meals, 3 vehicles, 4 min | Assumptions; no real AV integration |
| Simulated robot range, capacity, speed | 2 mi, 20 meals, 3.5 mph | Assumptions |
| Meals per insulated tote | 10 | Assumption |
| Mode score weights, handoff burden, reliability prior | see `assumptions.py` | Assumptions; reliability blends observed completion rates |
| Routing fallback | haversine x 1.3 at 30 km/h | Build spec |
| Matching radius | 15 mi | Assumption |
