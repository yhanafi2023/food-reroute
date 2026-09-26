# FoodFlow progress

## Dev 4: AI and optimization (`backend/app/intelligence/`)

**Done (branch `dev4-intelligence`)**
- `allocate(meals, candidate_needs)`: greedy split by priority, deadline, distance; max 3 stops; leftover to best need.
- `demand_fit(meals, allocations, candidate_needs)`: helper for the logistics score.
- Synthetic data generator, training (time split, LR vs GradientBoosting, best by ROC AUC, joblib), `predict_surplus`, `forecast_tonight`, `model_info`, `ensure_model` (trains when the model file is missing).
- `compute_impact(db)` over `impact_events`.
- `backend/tests/test_intelligence.py`: 13 tests, all green.
- Section README: `backend/app/intelligence/README.md`.

**Next:** fold the intelligence README into the root README in phase 7. Help Dev 3 wire `allocate` into matching.

### Notes for teammates

**Dev 2 (backend):**
- Add to `backend/requirements.txt`: `pandas`, `numpy`, `scikit-learn`, `joblib` (plus your `sqlalchemy`, `pytest`).
- `impact_events` needs these columns (compute_impact reads them with plain SQL): `delivery_id`, `restaurant_id`, `organization_id`, `meals`, `weight_lbs`, `delivery_minutes` (accepted_at to this drop off), `is_demo_seed`. Write one row per confirmed drop off. Seed the past demo deliveries with `is_demo_seed = true`.
- On startup call `app.intelligence.ensure_model()` so the first `/ml` request doesn't pay for training.
- Routes: `POST /ml/predict` → `{"probability": predict_surplus(body)}`; `GET /ml/forecast` → `forecast_tonight(restaurant_rows)` (reads `name`, and `food_category` or `cuisine`, `seats`, `hist_surplus_rate` when present; falls back to defaults); `GET /ml/info` → `model_info()`; `GET /impact` → `compute_impact(db)`.
- Env: `MEAL_VALUE_USD` (assumption, default 3.0) and optional `SURPLUS_MODEL_PATH`. Please add both to `backend/.env.example`.
- Imports work with `app` as a namespace package. If you add `backend/app/__init__.py`, nothing changes.

**Dev 3 (logistics):**
- `candidate_needs` can be dicts or ORM rows with `id`, `meals_needed`, `meals_fulfilled`, `priority`, `deadline`. Add `distance_miles` (restaurant to organization) so ties break by distance.
- The result is in rank order, not driving order; order the stops by nearest neighbor on your side.
- `demand_fit(meals, allocations, needs)` gives the `demand_fit` score term and doesn't count leftover meals pushed over a need.

**Dev 1 (frontend):**
- `/ml/info` returns `model_name`, `roc_auc`, `roc_auc_by_model`, `data`, and `note`. Show the "Prototype model, synthetic training data" label next to the forecast table.
- Label `community_value_estimate_usd` as an estimate.
