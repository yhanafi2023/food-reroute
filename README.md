# FoodFlow

**Good Food. Greater Impact.** Food rescue logistics for restaurants, receiving organizations (food banks, shelters,
community fridges, pantries) and the people who carry the food: volunteers, and SIMULATED autonomous vehicles and
sidewalk robots. Built for ShellHacks 2026 at FIU; demo city Miami-Dade.

- Practicality for staff, volunteers and coordinators: [docs/PRACTICALITY.md](docs/PRACTICALITY.md)
- Autonomous delivery (simulated, no Waymo API) and the fleet comparison: [docs/AUTONOMY.md](docs/AUTONOMY.md)
- Donor benefits (tax estimates, acknowledgments, liability, SB 1383): [docs/DONOR_BENEFITS.md](docs/DONOR_BENEFITS.md)
- Organization interview template: [docs/ORG_RESEARCH.md](docs/ORG_RESEARCH.md)
- What is real, simulated or fictional: [DATA_SOURCES.md](DATA_SOURCES.md)

> Status: backend and frontend both use the current API. The Playwright demo (`e2e/`) passes 3 runs in a row.
> See [PROGRESS.md](PROGRESS.md).

## Setup

Backend (Python 3.10+; on macOS use Homebrew's `python3.13`, since the Command Line Tools Python 3.9 cannot reach
OSRM over TLS):

```bash
cd backend
python3.13 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload --port 8000     # API docs at http://localhost:8000/docs
.venv/bin/pytest                               # 108 tests
```

With `DEMO_MODE=true` (default) an empty database is seeded with fictional accounts and a demo history produced by
the real services (see `backend/app/seed.py` for sign-in details). `python -m app.seed` resets it.

## Environment variables (`backend/.env`)

| Variable | Default | Purpose |
|---|---|---|
| `DATABASE_URL` | SQLite file | `postgresql://...` for Postgres |
| `JWT_SECRET` | dev value | Signs sessions; set a long random value anywhere public |
| `DEMO_MODE` | `true` | Seed fictional demo data; allow the demo sign-in code for demo accounts |
| `TIMEZONE` | `America/New_York` | Local time for receiving hours and schedules |
| `CORS_ORIGINS`, `FRONTEND_URL` | localhost:3000 | Allowed origins; magic-link base URL |
| `RUN_SCHEDULER`, `SCHEDULER_SECONDS` | `true`, `30` | Background checks (no-shows, expiry, vehicles, reports) |
| `ROUTING_SERVICE_URL` | empty | Teammate routing service (`POST /eta`); empty uses the in-process ETA model |
| `ALLOCATION_SERVICE_URL` | empty | Teammate allocation service (`POST /allocate`); empty uses the in-process allocator |
| `SERVICE_TIMEOUT_SECONDS` | `3` | Before falling back (results flagged `estimated: true`) |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | empty | Email notifications (console otherwise) |
| `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_FROM` | empty | Optional SMS |
| `LOAD_WINDOW_MIN`, `NO_SHOW_GRACE_MIN`, `AV_CAPACITY_MEALS`, ... | see `app/assumptions.py` | Assumptions, served at `GET /config/assumptions` |
| `MAPBOX_ACCESS_TOKEN`, `ROUTING_PROVIDER`, `OSRM_URL` | | Map routes (`app/logistics/routing.py`) |

## Try it with curl

```bash
API=http://localhost:8000
# sign in (the code arrives by the console/email provider; demo accounts may use the demo code in app/seed.py)
curl -s -X POST $API/auth/request-code -H 'content-type: application/json' -d '{"email":"staff@casa-demo.example.com"}'
TOKEN=$(curl -s -X POST $API/auth/verify -H 'content-type: application/json' \
  -d '{"email":"staff@casa-demo.example.com","code":"<code>"}' | python3 -c 'import sys,json;print(json.load(sys.stdin)["token"])')

# quick post: quantity + unit + category + deadline + attestation
curl -s -X POST $API/rescues -H "Authorization: Bearer $TOKEN" -H 'content-type: application/json' \
  -H 'Idempotency-Key: post-001' \
  -d '{"quantity":2,"unit":"tray","category":"hot","attested":true,"pickup_deadline":"2026-09-27T03:00:00Z"}'

# why each organization could or could not take it
curl -s $API/rescues/1/matching-explanation -H "Authorization: Bearer $TOKEN"
```

## Run the demo scenarios

- `python -m app.seed` rebuilds the fictional seed and replays five scenarios on the previous evening: a completed
  rescue with a full audit trail, a volunteer no-show that re-queued, a partial acceptance, a late-night simulated AV
  delivery, and a missed AV load window with a volunteer fallback. Open `GET /rescues/{id}/audit` as a restaurant.
- `GET /analytics/compare-fleets` (admin) runs the seeded volunteer-only vs mixed-fleet evening; the committed
  output is `docs/compare-fleets-run.json`.
- `python -m scripts.walkthroughs` re-measures the persona walkthroughs in `docs/PRACTICALITY.md`.

## API overview

| Area | Endpoints |
|---|---|
| Sign-in and members | `POST /auth/request-code`, `POST /auth/verify`, `GET /auth/me`, `POST /auth/register-organization`, `POST /auth/register-volunteer`, `GET/POST /orgs/me/members`, `DELETE /orgs/me/members/{id}` |
| Onboarding | `PUT /orgs/me/intake/{Q1,Q2,Q3}`, `POST /orgs/me/intake/confirm`, `GET /orgs/me/profile`, `GET /orgs/{id}/profile-completeness`, `POST /orgs/me/need`, `POST /admin/orgs/{id}/verify-ein`, `GET/PUT /restaurants/me/profile`, `GET/PUT /volunteers/me/profile` |
| Posting | `POST /rescues`, `POST /rescues/repeat-last`, `GET/POST /restaurants/me/templates`, `POST /rescues/from-template/{id}`, `POST /restaurants/me/schedules`, `POST /rescues/{id}/confirm`, `PATCH /rescues/{id}`, `POST /rescues/{id}/cancel` |
| Matching | `GET /rescues/{id}/matching-explanation`, `GET /fleet/availability` |
| Handoffs | `GET /volunteers/me/trips`, `POST /trips/{id}/accept`, `/decline`, `/cancel`, `/pickup`, `POST /stops/{id}/deliver`, `/report-closed`, `GET /orgs/me/deliveries`, `GET /stops/{id}/receipt-form`, `POST /stops/{id}/receipt`, `/refuse`, `/meals-served`, `POST /trips/{id}/curb/unlock`, `/curb/loaded`, `/curb/unloaded`, `PATCH /volunteers/me/location` |
| Records | `GET /rescues/{id}/audit`, `GET /reports/donor-tax-summary`, `GET /acknowledgments`, `GET /acknowledgments/{id}`, `POST /acknowledgments/{id}/sign`, `POST /restaurants/me/agreements`, `GET /reports/sb1383`, `GET /restaurants/me/benefits`, `POST /restaurants/me/totes/returned`, `GET /public/partners/{slug}`, `GET/POST /orgs/me/reports`, `GET /orgs/me/reports/{id}/download`, `GET /orgs/me/incomplete-deliveries`, `GET /volunteers/me/hours` |
| Notifications | `GET/PUT /me/notification-preferences`, `GET /me/notifications` |
| Analytics and admin | `GET /analytics/coverage`, `/compare-fleets`, `/matching-rejections`, `POST /admin/jobs/run`, `GET /config/assumptions` |
| Prospects (research, not partners) | `GET /prospects`, `/prospects/meta`, `/prospects/opportunities`, `/prospects/{id}`, `PUT /prospects/{id}/surplus-log`, `GET/PUT /restaurants/me/surplus-log` |

All state-changing endpoints accept an `Idempotency-Key` header. Illegal state changes return 409.

## Driver ETA and live tracking

Matching, the simulated fleets and the fleet comparison use an ETA model trained on 27,172 real OSRM road-network travel times in
Miami-Dade: gradient boosting for the P50 (2.8 min average error on held-out places vs 10.0 for the old 22 mph
rule) and conformal-calibrated quantile models for a P10 to P90 range, plus an assumed 6 minutes per handling stop.
Volunteers can share live location (`PATCH /volunteers/me/location`). Details: [DATA_SOURCES.md](DATA_SOURCES.md).

## Miami prospect directory

The prospect API lists 14 researched businesses near FIU with sources, dates checked, contact details, evidence
level and "unknown" wherever data is missing. They are not partners. Businesses are ranked only after a measured
quantity exists; the seven-day surplus log (also `PUT /restaurants/me/surplus-log` for enrolled restaurants) produces one.

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
