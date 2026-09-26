# FoodFlow — System Context (as of this session)

Branch: `community-need-intelligence`. Nothing committed — 47 files changed/added, uncommitted.

## Poverty dataset — confirmed real
`backend/data/census_tracts_miami_dade.json` — **540 KB, 123 real Census tracts**, fetched live this
session via your Census API key (stored server-side only in `backend/.env` as `CENSUS_API_KEY`).

- Source: `U.S. Census Bureau, 2024 ACS 5-Year Estimates (Table S1701, Poverty Status in the Past 12
  Months)`. Geometry from TIGERweb (keyless).
- `fetched_at`: 2026-09-26T15:35:25Z
- Poverty rate across the 123 tracts: min 1.5%, median 10.7%, max 39.2%.
- 3 tracts dropped for population < 50 (statistically meaningless, e.g. one had population 4).
- Regenerate anytime: `cd backend && .venv/Scripts/python.exe -m scripts.import_census_tracts`.
- Each tract: `{geoid, name, poverty_rate, margin_of_error_pct, population, population_below_poverty,
  bucket (low/moderate/high/very_high — our buckets, not official Census ones), community_need_score
  (0-1, poverty_rate/40 clamped), geometry}`.

## Backend (`backend/`, FastAPI + SQLAlchemy, SQLite by default)

**Run it**: `cd backend && .venv/Scripts/python.exe -m uvicorn app.main:app --reload --port 8000`
**Reset demo data**: `.venv/Scripts/python.exe -m app.seed`
**Tests**: `.venv/Scripts/python.exe -m pytest tests/ -q` → 119/119 passing

**Data model** (`app/models.py`): `Organization` (kind=restaurant|receiver) → `RestaurantProfile` /
`ReceiverProfile`; `User` (roles: restaurant_staff/restaurant_manager, volunteer, org_staff/org_manager,
admin); `Rescue` → `Trip` → `TripStop`; `MatchingExplanation` (now carries a `score` JSON column);
`ImpactEvent`, `Notification`, `AuditEvent`, `SurplusLog`, etc.

**Auth**: passwordless. `POST /auth/request-code` {email} → 6-digit code + magic link (console-logged
in dev). `POST /auth/verify` {email,code} or {token}. Demo accounts also accept the fixed code
`246810` (see `app/seed.py` for all demo logins, e.g. `manager@casa-demo.example.com`).

**Matching pipeline**: `POST /rescues` → `app/dispatch.py::run_matching` → `app/eligibility.py::check`
(hard constraints: hours, food category, allergens, capacity, distance — eliminates candidates
entirely) → `app/intelligence/allocation.py::rank_candidates`/`score_need` (weighted ranking among
already-eligible orgs: distance/urgency/demand/capacity/**community_need**, weights in
`app/assumptions.py::MATCHING_WEIGHTS`) → `Trip`/`TripStop` created. Same allocation module also
backs the legacy demo-only `app/logistics/matching.py` ("Simulate Tonight" engine).

**Community-need feature**: `app/community_need.py` (tract lookup, scoring, disclaimer text) +
`app/routes/community_need.py` (`GET /community-need/areas`, `GET /community-need/organizations/{id}`)
+ `GET /rescues/{id}/matching-explanation?weights=community_need_priority` (read-only what-if
re-weighting, doesn't touch the real trip).

**Other new endpoints this session**: `GET /admin/network` (restaurants/orgs/volunteers/active
trips, admin-only), `GET /impact` (public, was written but never routed before).

**Full route list**: run the app and see `/docs` (FastAPI auto docs), or `grep -rn "@router\." app/routes`.

## Frontend (`frontend/`, Next.js 16 App Router + Leaflet)

**Run it**: `cd frontend && npm run dev` (port 3000). `.env.local` has `NEXT_PUBLIC_API_URL=http://localhost:8000`.
No more mock-data mode — it talks to the real backend now (`lib/mock.ts` deleted).

**Pages**: `/login`, `/signup`, `/auth/callback` (magic link), `/restaurant/dashboard`,
`/restaurant/surplus-log`, `/volunteer/dashboard` (was `/driver`), `/organization/dashboard`,
`/organization/onboarding` (Q1/Q2/Q3 intake form), `/admin/dashboard` (network map + Community Impact
Mode + community-need choropleth toggle), `/admin/prospects`, `/impact`, `/qr`.

**Key files**: `lib/types.ts` (mirrors real backend JSON), `lib/auth.tsx` (passwordless flow),
`components/MapView.tsx` (map + the community-need choropleth layer/legend/toggle),
`components/MatchCard.tsx` + `WhyThisMatch.tsx` (match result + score breakdown/alternatives),
`components/RescueSequence.tsx` (the cinematic "finding a match" animation).

**Verification done**: `tsc --noEmit`, `eslint`, `next build` all clean; Playwright smoke-tested login
→ post rescue → real match with community-need scoring → admin map choropleth → volunteer/org
dashboards, zero console errors. Demo DB was reset to a clean seed after testing.

## Known simplifications (real API limits, not bugs)
- No routed polylines from the backend → delivery maps draw straight lines restaurant→stops.
- Volunteer live GPS is admin-only by the backend's own design (`app/views.py`) → restaurant/org
  maps don't show a moving carrier dot, only fixed points.
