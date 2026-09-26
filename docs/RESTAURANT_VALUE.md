# What a restaurant gets back

Restaurants give safe surplus food to neighbors in need instead of throwing it away. FoodFlow makes that the easy
default at closing time and shows the restaurant what it got back. Every number comes from the restaurant's own
entered data or recorded history, with its formula. Anything without inputs says "Add your info to see this".
Nothing is guessed.

## Zero effort

- **Closing-time nudge**: at each restaurant's own local closing time minus `nudge_minutes_before` (default 30), staff
  get "Any surplus tonight? Tap to repeat last post." Per-restaurant time zone and opt-out
  (`PUT /restaurants/me/value-settings`); users can also mute the event.
- **One tap**: repeat last post (`POST /rescues/repeat-last`) and templates generated from the menu
  (`POST /restaurants/me/templates/from-menu`).
- **Pickups at closing, never mid-service**: a post can name its earliest pickup, or the restaurant turns on
  "pickups after closing". Food safety wins: if waiting until closing would pass the food's safe-until time (minus 30
  minutes), FoodFlow does not delay and says why.
- **Reusable totes**: FoodFlow lends totes (`POST /admin/restaurants/{id}/totes/lend`); totes sent with vehicle trips
  and returns are recorded in a ledger (`GET /restaurants/me/totes`).
- **Time to post**: the app sends when the form was opened; FoodFlow stores the seconds to submit
  (`GET /restaurants/me/post-timing`). **No real usage has been recorded yet**, so there is no median to report;
  it will come from real use, not an estimate.

## Buy less food: over-prep insights

From the restaurant's own posts per menu item and local weekday (`GET /restaurants/me/insights`):

- Nothing is suggested until there are 4 weeks of history.
- A weekday pattern needs surplus on at least 60% and at least 4 of the last (up to) 10 such weekdays.
- Cards are worded as patterns in their data, not guarantees. Trends compare the last 4 weeks with the 4 before.
  If the restaurant enters a typical batch size, the unsold share of a batch is shown.
- A forecast appears only if a prediction service is configured (`PREDICTION_SERVICE_URL`), with its source label.
  FoodFlow does not show forecasts from its synthetic prototype.
- **Savings after "tried it"** (`POST /restaurants/me/insights/tried`):
  `estimated_food_cost_saved = (baseline_surplus - current_surplus) x cost_per_unit`, with the baseline over the 4
  weeks before "tried it", the current value over the full weeks since, and the item's own cost (actual cost, or
  menu price x food cost %). Labeled estimated; season and menu changes also matter.

## Lower trash bills

Avoided hauling = pounds donated x the restaurant's own cost per pound, shown only when the restaurant entered one.
If it entered its container size and pickups per week, a "right-size your dumpster" note appears only when the
weekly diverted volume is at least half a container (pounds / 396 lbs per cubic yard, the EPA "Food Waste -
restaurants" factor from its April 2016 Volume-to-Weight Conversion Factors memo), and it says to ask the hauler.
The half-container threshold is an assumption.

## Monthly "What you got back" report

`GET /restaurants/me/value-report?month=YYYY-MM` (JSON or PDF; managers get a notification on the 1st). Lines:
food cost saved from prep changes, avoided hauling, extra tax deduction vs throwing it away plus estimated tax saved
(from the tax module), compliance status (unsigned acknowledgments, items needing valuation, written agreement),
and community impact (meals, pounds at 1.2 lbs per meal from Feeding America, partner organizations served). The
"estimated total value this month" adds only dollar lines with real inputs, and adds estimated tax saved, not the
deduction itself.

### Demo result (fictional data, from a real run)

The seed gives Casa Demo Cocina (fictional) three months of history, June to August 2026, all posted, matched,
delivered and received through the real services: 3 trays of rice every Monday until it marked the Monday rice
suggestion "tried it" on 2026-07-28, then 1 tray every Monday in August, plus a half pan of roast chicken every other
Thursday. It entered a hauling cost of $0.08 per lb and a 21% tax rate; its fictional menu values rice at $60 a tray
with a 30% food cost.

Before "tried it", the insight read: "Rice and black beans: surplus on 9 of the last 9 Mondays, averaging 3.0 trays.
Consider preparing less on Mondays."

The August 2026 report, as computed (`backend/tests/test_seed.py` checks the lines are all present):

| Line | Value | How |
|---|---|---|
| Food cost saved from prep changes | $159 (estimated) | (3.0 - 1.0 trays per week) x $18 cost per tray x 4.43 weeks in August after "tried it" |
| Avoided hauling | $8 (estimated) | 96 lbs donated x $0.08 per lb (entered) |
| Extra tax deduction vs throwing it away | $150 (estimate) | sum of enhanced deduction - basis over accepted items |
| Estimated tax saved | $32 | $150 x 21% (rate entered) |
| Compliance | records complete | acknowledgments signed, items valued, agreement uploaded |
| Community impact | 80 meals, 96 lbs, 1 partner organization | meals x 1.2 lbs (Feeding America) |
| **Estimated total value this month** | **$199** | food cost saved + avoided hauling + estimated tax saved |

## Free marketing, opt-in only

- Public partner page (`GET /public/partners/{slug}`): meals donated to date, pounds diverted, and receiving
  organizations only if they consented to be named (`PUT /orgs/me/public-naming`); others are counted, not named.
  People served are never shown.
- Monthly 1080x1080 social card PNG with the restaurant's real number ("This month we shared N meals with neighbors in
  need instead of throwing them away."), off by default, downloadable only after the restaurant approves that month.
- QR window decal linking to the partner page, only when the page is on.
