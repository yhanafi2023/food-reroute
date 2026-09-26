# FoodFlow progress

Last updated 2026-09-26.

## Done

- **Dev 4, intelligence**: allocation (split delivery), synthetic data + LR vs GradientBoosting forecast,
  `predict_surplus`, `forecast_tonight`, `model_info`, impact. Merged in PR #1.
- **Dev 3, logistics**: `find_best_match` (top-k prefilter, contract score, deadline rejection, reasons, top 3
  candidates), `run_batch` (earliest deadline first), `get_route` (Mapbox Directions → OSRM → offline fallback,
  cached), `next_status`.
- **Dev 2, backend**: FastAPI, SQLAlchemy models with CHECK constraints and indexes, Postgres/PostGIS schema, JWT
  auth with role + ownership checks, every contract endpoint, demo seed, `/demo/reset` (~40 ms), deterministic
  Simulate Tonight.
- **Dev 1, frontend**: Next.js app in `frontend/`, typed API client + mocks, every page in the spec, map with
  numbered stops and moving drivers, "Why this match?" panel, Simulate Tonight playback. `npm run build` and
  `eslint` clean.
- **Shared**: 34 backend tests green; Playwright demo test passes 3 times in a row; `start.sh`; DEMO.md,
  README.md, PITCH.md, DEVPOST.md; `render.yaml`.

- **Miami focus (branch `miami-prospects-eta`)**: researched prospect directory near FIU with sources
  (DATA_SOURCES.md), seven-day surplus log, measured-only ranking; ETA model trained on 27,172 real OSRM
  road-network times; live tracking with GPS sharing or estimated position; Uber-style navigation with a
  full-screen mobile menu; cancellable requests, live status, retry, loading placeholders; simulation stop/restart.
  46 backend tests, 4 Playwright tests x3 all passing.

- **Practicality backend (branch `practicality-backend`)**: organizations with staff/manager roles, passwordless
  sign-in, onboarding intake (Q1-Q3), quick post with kitchen units and safety attestation, intake-driven
  eligibility with explanations, lifecycle state machine with pickup/drop-off codes, append-only audit trail,
  idempotency keys, failure handling, simulated AV/robot fleet with curbside handoff, analytics and fleet
  comparison, donor tax estimates and acknowledgments, SB 1383 records, org reports, volunteer hours,
  notifications. 108 backend tests passing. Docs in `docs/`.

## In progress

- Nothing on the backend.

## Needs a teammate (frontend, Dev 1)

The backend API changed; the Next.js app in `frontend/` and `e2e/` still target the old API and will not work
until updated. Key changes:
- Sign-in: `POST /auth/login` {email, password}; registration takes a password and returns a session.
  No email is sent. Demo accounts and the demo password are listed in `backend/app/seed.py`.
- Roles: restaurant_staff, restaurant_manager, volunteer, org_staff, org_manager, admin.
- Posting: `POST /rescues` with quantity, unit, category, pickup_deadline, attested (see README API overview).
- Lifecycle: posted, matched, en_route_pickup, picked_up, en_route_dropoff, delivered, received (+ exits);
  carriers act on `/trips/{id}/...` and `/stops/{id}/...` with codes; orgs confirm with `/stops/{id}/receipt`.
- Receiving orgs must complete `PUT /orgs/me/intake/Q1..Q3` before they receive anything.
- DEMO.md, PITCH.md and DEVPOST.md describe the previous flow and need a pass after the frontend is updated.

## Blocked / needs a person

- **Deploy**: needs the team's Render and Vercel accounts. Steps in README "Deploy".
- **Mapbox**: put the token in `backend/.env` as `MAPBOX_ACCESS_TOKEN` (server routing). For Mapbox map tiles, a
  public `pk.` token goes in `frontend/.env.local` as `NEXT_PUBLIC_MAPBOX_TOKEN`. Never commit either file.
- **Measured surplus**: none published for any researched business; needs businesses to complete the seven-day log.
- **Statistics**: fill every `[SOURCE NEEDED]` in PITCH.md and DEVPOST.md from USDA, ReFED or Feeding America.
- **MEAL_VALUE_USD**: 3.0 is a placeholder assumption; replace it with a sourced value.
- **Sponsor challenges**: none chosen yet; add them to DEVPOST.md.

## Next

1. Deploy (Render + Vercel), then run the e2e test against the deployed URLs.
2. Record the backup demo video.
3. Screenshots into the README.
4. Practice the pitch with the timings in PITCH.md.
