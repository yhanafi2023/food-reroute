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

## In progress

- Nothing.

## Blocked / needs a person

- **Deploy**: needs the team's Render and Vercel accounts. Steps in README "Deploy".
- **Mapbox**: put the token in `backend/.env` as `MAPBOX_ACCESS_TOKEN` (server routing). For Mapbox map tiles, a
  public `pk.` token goes in `frontend/.env.local` as `NEXT_PUBLIC_MAPBOX_TOKEN`. Never commit either file.
- **Statistics**: fill every `[SOURCE NEEDED]` in PITCH.md and DEVPOST.md from USDA, ReFED or Feeding America.
- **MEAL_VALUE_USD**: 3.0 is a placeholder assumption; replace it with a sourced value.
- **Sponsor challenges**: none chosen yet; add them to DEVPOST.md.

## Next

1. Deploy (Render + Vercel), then run the e2e test against the deployed URLs.
2. Record the backup demo video.
3. Screenshots into the README.
4. Practice the pitch with the timings in PITCH.md.
