"""SYNTHETIC training data for the surplus forecast prototype.

EVERY ROW HERE IS MADE UP. No real restaurant supplied this data. It exists so
the pipeline (features, time based split, model selection, serving) is real and
can be retrained on partner restaurants' actual history later.

Shape: 12 fictional restaurants x 180 days x evening hours 18..23 = 12,960 rows.

Features:
  day_of_week        0 = Monday .. 6 = Sunday
  hour               18..23, the hour the kitchen checks what is left
  food_category      bakery, buffet, cuban, deli, pizza, sushi
  seats              restaurant size
  rain               1 if it rained that evening (fewer walk in customers)
  local_event        1 if there was a nearby event (extra food prepared)
  hist_surplus_rate  the restaurant's own surplus rate over the previous 28 days,
                     computed only from past rows so nothing leaks from the future
Label:
  surplus            1 if the restaurant had at least 10 surplus meals

Hidden rule the model has to find (plus Poisson and Gaussian noise):
  weekends, rain, local events, bigger dining rooms, buffets and bakeries, later
  hours, and a hidden per restaurant "over prep" habit all raise expected surplus.
  Buffets react more strongly to local events, an interaction that a linear model
  cannot fully capture.
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

SEED = 42
N_DAYS = 180
START_DATE = date(2026, 1, 5)  # a Monday
HOURS = list(range(18, 24))
SURPLUS_THRESHOLD_MEALS = 10

CATEGORY_EFFECT = {"bakery": 0.35, "buffet": 0.45, "cuban": 0.10, "deli": 0.15, "pizza": 0.0, "sushi": -0.25}
HOUR_EFFECT = {18: -0.45, 19: -0.25, 20: 0.0, 21: 0.25, 22: 0.4, 23: 0.2}

# Fictional restaurants. Names are placeholders, not real businesses.
RESTAURANTS = [
    ("Synthetic Bakery A", "bakery", 40),
    ("Synthetic Bakery B", "bakery", 60),
    ("Synthetic Buffet A", "buffet", 220),
    ("Synthetic Buffet B", "buffet", 160),
    ("Synthetic Cuban A", "cuban", 90),
    ("Synthetic Cuban B", "cuban", 130),
    ("Synthetic Deli A", "deli", 50),
    ("Synthetic Deli B", "deli", 80),
    ("Synthetic Pizza A", "pizza", 70),
    ("Synthetic Pizza B", "pizza", 120),
    ("Synthetic Sushi A", "sushi", 60),
    ("Synthetic Sushi B", "sushi", 100),
]

FEATURES_CATEGORICAL = ["food_category", "day_of_week", "hour"]
FEATURES_NUMERIC = ["seats", "rain", "local_event", "hist_surplus_rate"]
FEATURES = ["day_of_week", "hour", "food_category", "seats", "rain", "local_event", "hist_surplus_rate"]
LABEL = "surplus"

HIST_WINDOW_ROWS = 28 * len(HOURS)
HIST_PRIOR = 0.3


def generate(seed: int = SEED) -> pd.DataFrame:
    """Build the synthetic dataset. The same seed always gives the same rows."""
    rng = np.random.default_rng(seed)
    days = [START_DATE + timedelta(days=i) for i in range(N_DAYS)]

    # Weather and events are shared by every restaurant on the same evening.
    rain_by_day = rng.random(N_DAYS) < 0.35
    event_by_day = rng.random(N_DAYS) < 0.10
    over_prep = rng.normal(0.0, 0.3, len(RESTAURANTS))

    rows = []
    for r_idx, (name, category, seats) in enumerate(RESTAURANTS):
        for d_idx, day in enumerate(days):
            dow = day.weekday()
            rain = int(rain_by_day[d_idx])
            event = int(event_by_day[d_idx])
            for hour in HOURS:
                effect = (
                    {4: 0.35, 5: 0.45, 6: 0.25}.get(dow, 0.0)
                    + 0.3 * rain
                    + 0.25 * event
                    + (0.45 * event if category == "buffet" else 0.0)
                    + 0.35 * (seats - 110) / 100
                    + CATEGORY_EFFECT[category]
                    + HOUR_EFFECT[hour]
                    + over_prep[r_idx]
                    + rng.normal(0.0, 0.25)
                )
                surplus_meals = int(rng.poisson(np.exp(1.65 + effect)))
                rows.append(
                    {
                        "date": day.isoformat(),
                        "restaurant": name,
                        "day_of_week": dow,
                        "hour": hour,
                        "food_category": category,
                        "seats": seats,
                        "rain": rain,
                        "local_event": event,
                        "surplus_meals": surplus_meals,
                        LABEL: int(surplus_meals >= SURPLUS_THRESHOLD_MEALS),
                    }
                )

    df = pd.DataFrame(rows).sort_values(["restaurant", "date", "hour"]).reset_index(drop=True)
    # Past only rolling rate: shift(1) so a row never sees its own label.
    df["hist_surplus_rate"] = (
        df.groupby("restaurant")[LABEL]
        .transform(lambda s: s.shift(1).rolling(HIST_WINDOW_ROWS, min_periods=len(HOURS)).mean())
        .fillna(HIST_PRIOR)
        .round(3)
    )
    df["is_synthetic"] = True
    return df


def main() -> None:
    out = Path(__file__).resolve().parent / "data" / "surplus_synthetic.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    df = generate()
    df.to_csv(out, index=False)
    print(f"Wrote {len(df)} SYNTHETIC rows to {out} (positive rate {df[LABEL].mean():.1%})")


if __name__ == "__main__":
    main()
