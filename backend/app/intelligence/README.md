# Intelligence: allocation, surplus forecast, impact (Dev 4)

Folder: `backend/app/intelligence/`. It has no web framework imports. Routes call these functions:

| Function | Used by | Returns |
|---|---|---|
| `allocate(meals, candidate_needs)` | logistics `find_best_match` | `[{need_id, meals}]`, at most 3 stops |
| `demand_fit(meals, allocations, candidate_needs)` | logistics score | share of meals that met real need, 0 to 1 |
| `predict_surplus(features)` | `POST /ml/predict` | probability 0 to 1 |
| `forecast_tonight(restaurants)` | `GET /ml/forecast` | `[{restaurant, probability}]`, highest first |
| `model_info()` | `GET /ml/info` | model name, ROC AUC, "prototype trained on synthetic data" |
| `ensure_model()` | backend startup | loads the model, or trains it (a few seconds) when missing |
| `compute_impact(db)` | `GET /impact`, dashboards | Impact contract object |

Run the tests from `backend/`: `pytest tests/test_intelligence.py`.
Retrain by hand: `python -m app.intelligence.ml.train`. Export the CSV: `python -m app.intelligence.ml.generate_data`.

## Allocation: splitting one rescue across organizations

Needs are sorted by priority (HIGH first), then deadline (soonest first), then distance (nearest first). They are filled in that order without going over any need's remaining meals, up to 3 stops per trip. Meals left over after every chosen need is full go to the top ranked need, so food is never left at the restaurant. `demand_fit` does not count those extra meals.

Example (a required test): 50 meals, Food Bank needs 30 (HIGH), Shelter needs 20 → Food Bank 30, Shelter 20.

**Why greedy:** the rule is lexicographic ("most urgent organization first"), so filling in sorted order is exactly that rule, not an approximation of it. After the logistics prefilter there are at most about 5 candidate needs, so the cost is O(N log N) time and O(N) space, effectively constant.
**Stretch:** if priority, deadline and distance need to be traded off with numeric weights, or split across several rescues at once, it becomes a small linear program: maximize Σ wᵢxᵢ subject to Σ xᵢ ≤ meals and 0 ≤ xᵢ ≤ remainingᵢ (`scipy.optimize.linprog`).

## Surplus forecast (prototype, synthetic data)

**The training data is synthetic.** `ml/generate_data.py` generates 12 fictional restaurants × 180 days × evening hours 18 to 23 (12,960 rows) from a hidden rule plus noise. That gives the model a real pattern to learn, and it lets us show the pipeline working honestly. The label is "at least 10 surplus meals".

**Features and why:**
- `day_of_week`, `hour`: demand follows the weekly and nightly cycle, and surplus is known near closing.
- `food_category`: buffets and bakeries prepare in batches; sushi is made to order.
- `seats`: bigger kitchens prepare more.
- `rain`: fewer walk-in customers means more food left over.
- `local_event`: kitchens prepare extra food for nearby events. In the synthetic data, buffets respond more strongly (an interaction).
- `hist_surplus_rate`: the restaurant's own rate over the previous 28 days, computed from past rows only. It captures each kitchen's habit of over-preparing.

**Training:** time-based split, where the last 30 days are the test set, so the model is always scored on future evenings. Two scikit-learn Pipelines (OneHotEncoder for category, day and hour; StandardScaler for numbers) are trained: LogisticRegression and GradientBoostingClassifier. The one with the higher test ROC AUC is saved with joblib. Current run: GradientBoosting 0.870 vs LogisticRegression 0.868. The small gap shows the pattern is mostly additive, and boosting picks up the buffet × event interaction. The model trains automatically on first use if the file is missing (about 1 to 2 seconds).

**Cost:** gradient boosting trains in about O(n × trees × depth) after sorting the features and predicts in O(trees × depth) per row (150 trees, depth 3). Logistic regression trains in O(n × features × iterations) and predicts in O(features).

**Where it helps FoodFlow:** the admin forecast table shows which restaurants are likely to have surplus tonight, so drivers can be staged nearby before the food is posted.

**Honest note:** the AUC above measures how well the model recovers a rule we wrote ourselves. It says nothing about real restaurants. A real version would train on partner restaurants' actual surplus history (POS and waste logs) and would need recalibrating. The UI labels it "Prototype model, synthetic training data".

## Impact

`compute_impact(db)` aggregates the `impact_events` table (one row per confirmed drop off): meals, lbs, completed deliveries (distinct `delivery_id`), distinct restaurants and organizations, and average delivery minutes. A split delivery counts as finished at its last stop. Community value is meals × `MEAL_VALUE_USD`. **That is an assumption set in the environment (default 3.0 as a placeholder), not a measured number**, and it must be shown as an estimate. `includes_demo_data` is true if any event is demo seed data.
