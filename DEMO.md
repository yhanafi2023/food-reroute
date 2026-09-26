# FoodFlow 2 minute demo

Before you start: open the admin dashboard and click **Reset Demo** (or run `python -m app.seed` in `backend/`).
The "expiring soon" rescue is created 25 minutes from the reset, so reset right before presenting.
Routes use real roads (OSRM) when online and fall back to a labeled straight-line estimate with wifi off.
The demo accounts below are fictional; researched Miami businesses are only on the Prospects page.
Automated version of this exact path: `cd e2e && npm run test:3x`.

1. **Landing page** (`/`). Read the headline and point at the flow line: Restaurant, FoodFlow, Driver, Organization, Community. *(10 s)*
2. Click **Log in**, then **Restaurant** under Demo login. You are ABC Restaurant.
3. The form is prefilled with 50 meals and a deadline of 10 PM tonight. Tick the **food safety** box, click **Find a match**. *(15 s)*
4. "Finding the most efficient rescue match..." appears, then **Match found**: driver **Marcus**, stop 1 and stop 2 (**30 meals** to Community Food Bank, **20 meals** to Hope Shelter), miles and ETA chips, and the route on the map.
5. Scroll to **Why this match?**: three candidates, the chosen one highlighted, score breakdown bars for distance, ETA, urgency, demand fit and priority, plus plain English reasons. *(20 s)*
6. In a second window, log in as **Driver** (Marcus). The **New food rescue** card shows the offer. Click **Accept**.
7. The restaurant window now shows **Driver to pickup: About N min, likely A to B min** (ML ETA from real road-network data) and the driver's estimated position; turn on **Share live location** on the driver's phone to switch it to live GPS. Click the one big button through the steps: **I arrived at the restaurant**, **I picked up the food**, **Start delivering**, **Mark delivered**. The timeline fills in and every window updates without refreshing. *(20 s)*
8. Log in as **Organization** (Community Food Bank): "30 meals incoming, Driver: Marcus". Click **Confirm Receipt of 30 meals**. (Hope Shelter confirms its 20 with shelter@demo.com.) *(10 s)*
9. Open **Impact**: it counts only real deliveries confirmed by an organization, so the fictional demo run does not change it. Say so. *(5 s)*
10. Log in as **Admin**. Show the **Driver ETA model** panel (real OSRM data, 2.8 min error vs 10.0 for the old rule) and the surplus forecast marked "Needs real data". Click **Run Matching** to match the expiring soon bakery rescue and show urgency in its reasons. *(15 s)*
11. Click **Simulate Tonight**: 6 PM to 10 PM in 60 seconds (simulated). **Stop simulation** and **Restart simulation** control it. *(20 s)*
12. Open **Prospects**: 14 researched businesses near FIU with sources and dates checked, filters by neighborhood, type and evidence, and "unknown" where data is missing. Open Macchialina (named Food Rescue US donor) and show the seven-day log that turns a prospect into a ranked opportunity. *(15 s)*

Logins (password `demo1234`): restaurant@demo.com, driver@demo.com, org@demo.com, shelter@demo.com, admin@demo.com.
