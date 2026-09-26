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

## ShellHacks build (branch `shellhacks-demo`)

- **P0 done**: the frontend was rewritten against the current API (passwordless sign-in via the existing
  `/auth/request-code` and `/auth/verify`, unchanged). There are four role workspaces: restaurant `/restaurant`,
  volunteer `/volunteer`, receiving org `/org` and coordinator `/coordinator`. It also adds the magic-link page
  `/auth/callback` and the public partner page `/partners/[slug]`, both of which the backend links to. The
  landing page and a role picker at `/demo` round it out.
  - Backend additions (no existing endpoint changed):
    - a demo clock anchored at Friday 2026-09-25 7:00 PM Miami (`DEMO_CLOCK_START`, `real` to turn it off);
    - `GET /demo/state`, admin-only `POST /demo/clock` and `POST /demo/reset` (DEMO_MODE only);
    - `GET /time`.
  - Playwright: post, match, pickup with code (a wrong code is refused), drop off with code, org receipt, and a
    375px check. 3 of 3 runs passed. The measured restaurant posting time, from form ready to post confirmed with
    scripted clicks, was 162 to 164 ms. That is API plus UI latency, not a human's time.
  - Known issue: requests that arrive while a reset rebuilds the database can briefly fail
    (`no such table`); pages retry on their own.
- **Next**:
  - P1: coordinator map and heatmap, "Why this assignment?", ETA honesty, and the Tiger Data setup and hypertables.
  - P2: disruption panel, replay slider, live ops panel and Hot Zones (section 13).
  - P3: fair comparison, compression stats and the reliability aggregate.
  - P4: forecast presentation.

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
