# FoodFlow: Devpost submission

**Tagline:** Good Food. Greater Impact. Real time food rescue that matches restaurant surplus to the community
organizations that need it, and routes a driver before it expires.

## Inspiration

Restaurants near us throw away safe food at closing while food banks, shelters and campus pantries a few miles away
run short. [SOURCE NEEDED: US food waste statistic, ReFED] [SOURCE NEEDED: food insecurity statistic, USDA ERS].
The food and the need already exist in the same city. What is missing is the coordination: who needs it right now,
who can drive it there, and how to split it so nothing is wasted.

## What it does

- A restaurant posts surplus food (meals, weight, pickup deadline, food safety confirmation).
- FoodFlow picks the best volunteer driver and splits the food across organizations. For example, 30 meals go to a
  food bank with a high priority need and 20 to a shelter, in one trip.
- **"Why this match?"** shows the top 3 options with a score breakdown (distance, ETA, urgency, demand fit,
  priority) and plain English reasons.
- The driver accepts and taps one button per step. Every dashboard updates live with a status timeline and a map
  with numbered stops.
- Each organization confirms what it received, and only then does it count toward impact.
- Admins see the whole network, run batch matching, view a surplus forecast (prototype model, synthetic training
  data), and run **Simulate Tonight**: 6 to 10 PM in 60 seconds of simulated data using the real matching code.
- People receiving food never need the app; organizations are the bridge.

## How we built it

- **Frontend:** Next.js (App Router) with TypeScript and Tailwind, React Leaflet with Mapbox or OpenStreetMap
  tiles, polling for live updates, and a mock API mode so frontend work never waited on the backend.
- **Backend:** Python FastAPI, SQLAlchemy 2.0 on SQLite (Postgres/PostGIS schema ready), our own JWT auth with
  salted password hashing, role and ownership checks, and pydantic validation.
- **Logistics engine:** top-k nearest prefilter with heapq, a scoring function that trades distance and ETA against
  urgency, demand fit and priority, deadline rejection, earliest-deadline-first batch matching, a delivery state
  machine, and Mapbox Directions routing with a 3 second timeout, caching and an offline fallback.
- **AI and optimization:** a greedy priority allocator for split deliveries (at most 3 stops, never overfills a
  need), plus a surplus forecast pipeline in scikit-learn. It compares LogisticRegression and GradientBoosting on a
  time based split and keeps the better ROC AUC. The training data is synthetic and labeled as such.
- **Reliability:** deterministic seed data and simulation, a one click demo reset, offline mode, 34 backend tests,
  and a Playwright test that runs our exact demo click path, which passed 3 times in a row.

## Challenges we ran into

- Making split deliveries correct: two organizations confirm one delivery separately, and meals already promised to
  pending matches must not be promised again.
- Keeping alternatives honest: an early version sent all 50 meals to one food bank that needed 30 because the route
  was shorter. We now only compare plans that place every meal on real need.
- Making an optimization readable in seconds for a judge, a driver and a restaurant manager.
- Making a live demo that cannot break: deterministic data, offline routing and a scripted end to end test.

## Accomplishments that we're proud of

- The whole loop works end to end: post, match, split, route, accept, deliver, confirm, impact.
- Every match explains itself.
- Honest labeling everywhere: demo data, simulated data, synthetic training data, estimated value.

## What we learned

- Explainability is a feature. The same formula feels trustworthy once people can see the options it rejected.
- Simple, well chosen algorithms (heaps, greedy with a good prefilter, a state machine) go a long way in real time
  logistics.
- ML needs real data to be meaningful. We built the pipeline and were upfront that the data is synthetic.

## What's next for FoodFlow

1. SMS and phone access through organizations.
2. POS integrations so restaurants post surplus automatically at closing.
3. Train the forecast on real partner restaurant history.
4. Regional network: optimal batch assignment (Hungarian algorithm), multiple rescues per trip.
5. City wide food rescue infrastructure, including disaster response.

## Built with

Next.js, React, TypeScript, Tailwind CSS, Leaflet, React Leaflet, Mapbox (Directions API and map tiles),
OpenStreetMap, Python, FastAPI, SQLAlchemy, SQLite, PostgreSQL/PostGIS (schema), PyJWT, pydantic, pandas, NumPy,
scikit-learn, joblib, pytest, Playwright, Vercel, Render.

## Sponsor challenges

We are not entering any sponsor challenges yet. When we pick them, list each one here with exactly how FoodFlow
meets it (the feature, where to see it in the demo, and the sponsor technology used).

## Links

- Live demo: [ADD Vercel URL]
- API: [ADD Render URL]
- Repo: https://github.com/yhanafi2023/food-reroute
- Demo video: [ADD backup video link]
- Screenshots: [ADD to the repo README]
