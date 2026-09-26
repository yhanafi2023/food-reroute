# FoodFlow

**Good Food. Greater Impact.** A real time food rescue platform. Restaurants post safe surplus food, FoodFlow
matches it to the community organizations that need it (food banks, shelters, churches, school pantries), splits
the donation across them, and routes a volunteer driver before the food expires.

> There is food available right now. Who needs it, and how do we get it there before it goes to waste?

Restaurant → FoodFlow matching → Driver → Community organization → people served. People receiving food never
need the app or a smartphone; organizations are the bridge.

Built for ShellHacks 2026 at FIU. All numbers shown in the app are demo or simulated data unless stated otherwise.

## Quick start

One command (creates the venv, installs packages, copies env files, runs both servers):

```bash
./start.sh
```

Or by hand. Backend:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000
```

Frontend:

```bash
cd frontend
npm install
cp .env.example .env.local
npm run dev
```

Open http://localhost:3000. API docs: http://localhost:8000/docs.

**Demo logins** (password `demo1234`): restaurant@demo.com (ABC Restaurant), driver@demo.com (Marcus),
org@demo.com (Community Food Bank), shelter@demo.com (Hope Shelter), admin@demo.com. The 2 minute click path is in
[DEMO.md](DEMO.md).

## Tests

```bash
cd backend && .venv/bin/pytest                 # 34 tests: API flow, roles, logistics, allocation, ML, impact
cd e2e && npm install && npx playwright install chromium
npm run test:3x                                  # the DEMO.md click path, 3 times in a row
```

## Environment variables

Backend (`backend/.env`, see `backend/.env.example`):

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | `sqlite:///backend/foodflow.db` | SQLite locally; a `postgresql://` URL switches to Postgres |
| `JWT_SECRET` | dev value | Signs login tokens. Set a long random value anywhere public |
| `JWT_EXPIRE_HOURS` | `24` | Token lifetime |
| `DEMO_MODE` | `true` | Seed demo data when the database is empty; offline routing unless a Mapbox token is set |
| `CORS_ORIGINS` | `http://localhost:3000` | Comma separated frontend origins |
| `ROUTING_PROVIDER` | auto | `mapbox`, `osrm` or `offline`. Auto: mapbox with a token, offline in demo mode, else osrm |
| `MAPBOX_ACCESS_TOKEN` | empty | Mapbox Directions API token (server side) |
| `OSRM_URL` | `https://router.project-osrm.org` | OSRM server |
| `MEAL_VALUE_USD` | `3.0` | **Assumption** used for the community value estimate. Replace with a sourced figure |
| `SURPLUS_MODEL_PATH` | `app/intelligence/ml/artifacts/` | Where the forecast model is saved |

Frontend (`frontend/.env.local`, see `frontend/.env.example`): `NEXT_PUBLIC_API_URL`, `NEXT_PUBLIC_USE_MOCKS`
(run the UI with no backend), `NEXT_PUBLIC_MAPBOX_TOKEN` (public `pk.` token for map tiles; OpenStreetMap
otherwise), `NEXT_PUBLIC_SITE_URL` (for the QR page).

## API

JSON, snake_case, `Authorization: Bearer <token>`. Roles: RESTAURANT, DRIVER, ORGANIZATION, ADMIN. Every endpoint
checks role and ownership (a driver can only update their own delivery; an organization can only confirm its own stop).

| Endpoint | Who | What |
|---|---|---|
| `POST /auth/signup` | anyone | Create a restaurant, driver or organization account → `{token, user}` |
| `POST /auth/login` | anyone | → `{token, user}` |
| `GET /auth/me` | logged in | Current user |
| `POST /rescues` | restaurant | Create a rescue and run matching → `{rescue, match}` |
| `GET /rescues/available` | logged in | Open and matched rescues, soonest deadline first |
| `GET /rescues/{id}` | logged in | Rescue with its match and delivery |
| `POST /rescues/{id}/accept` | driver | Accept your offer → Delivery with a stored route |
| `POST /rescues/{id}/decline` | driver | Decline; rematches excluding you |
| `PATCH /deliveries/{id}/status` | driver, admin | Advance one step; 400 on illegal jumps |
| `POST /deliveries/{id}/confirm` | organization, admin | Confirm your drop off; updates needs and impact |
| `POST /organizations/needs` | organization | Post a need |
| `GET /organizations/needs` | logged in | Your needs (organizations) or open needs (others) |
| `GET /restaurants/dashboard` | restaurant | Stats and rescues |
| `GET /drivers/dashboard` | driver | Offer, active delivery, history |
| `GET /organizations/dashboard` | organization | Needs, incoming and received deliveries |
| `GET /admin/network` | admin | Every marker, active route, stats and impact |
| `PATCH /drivers/me/availability` | driver | Go online or offline (hands a pending offer to the next driver) |
| `GET /drivers/nearby?lat=&lng=&radius_miles=` | restaurant, org, admin | Available drivers by distance |
| `GET /impact` | public | Impact totals |
| `POST /matching/run` | admin | Batch match all open rescues |
| `POST /simulation/run` | admin | Timed events for Simulate Tonight |
| `POST /ml/predict` | admin, restaurant | Surplus probability for one set of features |
| `GET /ml/forecast` | admin | Tonight's surplus probability per restaurant |
| `GET /ml/info` | public | Model name, ROC AUC, synthetic data note |
| `POST /demo/reset` | admin | Restore the demo seed (about 40 ms) |

Status flow. Rescue: OPEN → MATCHED → ACCEPTED → PICKED_UP → DELIVERED → CONFIRMED (or EXPIRED, CANCELLED).
Delivery: HEADING_TO_RESTAURANT → ARRIVED_AT_RESTAURANT → PICKED_UP → DELIVERING → DELIVERED → CONFIRMED.
The driver is freed at DELIVERED; the delivery becomes CONFIRMED when every receiving organization has confirmed.

## Database

Tables: `users`, `restaurants`, `drivers`, `organizations`, `food_needs`, `food_rescues`, `matches`,
`match_stops`, `deliveries`, `impact_events`, with foreign keys and CHECK constraints on every status and
quantity. SQLAlchemy models: `backend/app/models.py`. Production schema with PostGIS:
`backend/db/schema_postgres.sql`.

| Index | Why |
|---|---|
| `drivers (is_available, lat, lng)` | Matching reads only available drivers near a pickup. Postgres: partial GIST index on `location WHERE is_available` |
| `food_needs (status, deadline)` | Matching and dashboards read open needs, soonest deadline first |
| `food_rescues (status, pickup_deadline)` | Batch matching and the expiry sweep read open rescues by deadline |
| `deliveries (driver_id, status)` | A driver's active delivery and history |
| `match_stops (organization_id, confirmed_at)` | Deliveries by organization: incoming vs received |
| `matches (driver_id, status)` | A driver's pending offer |

## How matching works (logistics, `backend/app/logistics/`)

Pure Python, no web framework imports.

**find_best_match(rescue, drivers, needs, exclude_driver_ids)**

1. Prefilter the 5 nearest available drivers with enough capacity and the 5 nearest open needs with
   `heapq.nsmallest`: O(D log k + N log k).
2. Build drop off plans with `intelligence.allocate` (the priority based split) plus a nearest-first split and a
   single stop run, kept only if they place every meal on real need. Stops are ordered by nearest neighbor.
3. Score every driver × plan (lower is better) and drop any driver who cannot reach the restaurant before the deadline:

```
score = pickup_mi + route_mi + 0.1 × eta_min × (1 + urgency) − 3 × demand_fit − 2 × priority_bonus
urgency        = clamp(1 − minutes_to_deadline / 180, 0, 1)
demand_fit     = meals placed on real need / meals available
priority_bonus = meal weighted HIGH 1, MEDIUM 0.5, LOW 0
```

4. Return the best Match with 3 to 4 plain English reasons and the top 3 candidates with their score breakdown
   (which sums to the score) for the "Why this match?" panel.

**Why greedy with a top k prefilter.** Food rescue is online: a rescue appears and needs an answer in seconds. Only
nearby drivers are realistic, so looking at k = 5 of them loses almost nothing and makes the cost independent of
fleet size after the prefilter. Scoring is O(k × plans) = constant. Space is O(k).

**Scaling.** Today the prefilter scans all D drivers and N needs in Python: O(D log k + N log k) time, O(D + N)
memory for the loaded rows. With PostGIS, `ORDER BY location <-> point LIMIT 5` on a GIST index is a KNN index
search, about O(log n + k), so the database returns only the 5 candidates and the rest of the algorithm is unchanged.

**run_batch** processes open rescues earliest deadline first with a min heap and greedily assigns drivers, tracking
filled needs as it goes: O(R log R + R × (D log k + N log k)). Greedy is fast but not globally optimal (an early
rescue can take a driver a later one needed more). The upgrade path is the Hungarian algorithm
(`scipy.optimize.linear_sum_assignment`) on an R × D score matrix, O(n³).

**get_route** calls the Mapbox Directions API (or OSRM) with a 3 second timeout and GeoJSON geometry, converts to
`[[lat, lng]]`, adds 6 minutes of handling per stop, and caches in memory. Any failure, or `ROUTING_PROVIDER=offline`,
returns the offline estimate: straight line × 1.3 at 22 mph plus 6 minutes per stop, `source: "offline"`.

**next_status** enforces the delivery order: only the single next step is legal.

## Allocation, forecast and impact (intelligence, `backend/app/intelligence/`)

Splitting a rescue across organizations (greedy by priority, deadline, distance; at most 3 stops), the surplus
forecast prototype trained on **synthetic** data (LogisticRegression vs GradientBoosting, time based split, best
ROC AUC kept), and impact metrics. Details, feature choices and complexity:
[backend/app/intelligence/README.md](backend/app/intelligence/README.md).

## Simulate Tonight

`POST /simulation/run` replays 6 PM to 10 PM in 60 seconds over the demo network using the real matching,
allocation and routing code with a fixed random seed, so it is identical every run. It never touches the database.
The admin map plays the events with `requestAnimationFrame`: rescues appear, drivers move along their routes,
meals split across organizations, counters count up. Labeled as simulated data.

## Deploy

- **Backend on Render**: `render.yaml` is a blueprint (Python web service, `DEMO_MODE=true`). Set `CORS_ORIGINS` to
  the Vercel URL and optionally `MAPBOX_ACCESS_TOKEN`. A Render Postgres `DATABASE_URL` also works
  (`pip install psycopg2-binary`).
- **Frontend on Vercel**: root directory `frontend`, env `NEXT_PUBLIC_API_URL=https://<render-app>.onrender.com`,
  optional `NEXT_PUBLIC_MAPBOX_TOKEN` and `NEXT_PUBLIC_SITE_URL`.

## Team and git workflow

| Folder | Owner |
|---|---|
| `frontend/` | Dev 1, frontend |
| `backend/app/` (routes, db, auth, seed, simulation) | Dev 2, backend |
| `backend/app/logistics/` | Dev 3, logistics and routing (Mapbox) |
| `backend/app/intelligence/` | Dev 4, AI and optimization |
| `backend/tests/`, `e2e/`, README, DEMO, PITCH, DEVPOST, PROGRESS | shared |

Protected `main`. One feature branch per developer (`dev1-frontend`, `dev2-backend`, ...). Small PRs, merge at
least every 2 hours, keep `pytest` and `npm run build` green before merging. Cross-folder requests go in
[PROGRESS.md](PROGRESS.md).

## Roadmap

MVP (this hackathon):
1. **Phase 1, hackathon MVP**: posting, matching with explanations, split delivery, routing, live status,
   confirmation, impact, surplus forecast prototype, simulation.

Stretch goals, in order:

2. **SMS and phone access through organizations**, so people and small pantries without smartphones can take part.
3. **Restaurant POS integrations** to post surplus automatically at closing.
4. **ML trained on real history** from partner restaurants, replacing the synthetic prototype.
5. **Regional logistics network**: batch optimization (Hungarian or LP), multiple rescues per trip, refrigerated vehicles.
6. **City wide food rescue infrastructure** with public agencies and disaster response mode.
