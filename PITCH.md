# FoodFlow pitch

Rule: never invent numbers. Every `[SOURCE NEEDED: ...]` is filled from USDA, ReFED or Feeding America before we
present. Every FoodFlow number on screen is demo or simulated data, and we say so.

## Team pitch (60 to 90 seconds)

**Problem (15 s).**
"Every night, restaurants throw away safe food, and a few miles away families go without dinner.
[SOURCE NEEDED: share or amount of US food that goes uneaten, ReFED] while
[SOURCE NEEDED: number of people in US food insecure households, USDA ERS]. The food and the need exist side by side."

**The coordination gap (15 s).**
"The hard part is not generosity, it is logistics. Surplus shows up at 9 PM with a two hour window. Someone has to
know who needs it, find a driver who is close, and split it so no food is left over and no pantry gets 50 meals it
can't store. Today that is phone calls and group chats."

**Live demo (45 s).** Follow DEMO.md steps 2 to 11, talking over it:
"ABC Restaurant posts 50 meals. In a second and a half FoodFlow matches Marcus, the closest driver, and splits the
food: 30 to the food bank with a high priority need, 20 to the shelter. Here is *why*: the three options it
compared, scored on distance, ETA, urgency, demand fit and priority. Marcus accepts, taps one button per step, and
everyone's screen updates live. Each organization confirms what it received, and impact updates. Now tonight at city
scale: Simulate Tonight replays 6 to 10 PM in 60 seconds, simulated data, running the same matching code."

**Technical depth (15 s).**
"Under the hood: a top-k nearest driver prefilter with a scoring function that weighs urgency against distance, a
greedy priority allocator for split deliveries, Mapbox road routing with an offline fallback so it works without
wifi, a state machine for every delivery, and a surplus forecast model. It is a prototype trained on synthetic data
and we label it that way."

**Impact and roadmap (10 s).**
"More food rescued, less waste, faster delivery, and people receiving food never need a smartphone. Next: SMS through
organizations, POS integrations, and training the forecast on real restaurant history."

## Developer pitches (20 to 30 seconds each)

**Dev 1, frontend.**
"I built every screen a restaurant, driver, organization and coordinator uses. The hard part was making a complex
decision readable in seconds: the 'Why this match?' panel turns a scoring formula into five bars and plain sentences.
Drivers get one big next step button, everything updates live every 3 seconds, and the map shows numbered stops
and a moving driver. Without it, the algorithm is invisible."

**Dev 2, backend.**
"I built the API and database: JWT auth with roles, ownership checks on every endpoint, and the workflow from
posting to confirmation. The hard part was correctness: two organizations confirming one split delivery, drivers
declining and rematching, needs never double counted. Tests cover the full flow, wrong roles and illegal status
jumps, and demo reset restores everything in under a second."

**Dev 3, logistics.**
"I built the matching engine: find the 5 nearest drivers and needs with a heap, score each option on distance, ETA,
urgency, demand fit and priority, and reject anyone who can't make the deadline. Routes come from Mapbox with a 3
second timeout and an offline fallback. The hard part was making it fast and explainable: every match comes with
reasons and the options it beat."

**Dev 4, AI and optimization.**
"I built how food is split and the surplus forecast. Allocation fills the most urgent needs first without
overfilling anyone, at most 3 stops. The forecast compares logistic regression and gradient boosting on a time
based split. The honest part: its data is synthetic, generated from a rule we wrote, so the score shows the pipeline
works, not that we can predict real restaurants yet. Real partner history is the next step."

## Judge Q&A

**How is this different from existing food donation apps?**
Most donation tools are listings: someone posts, someone else has to notice and arrange pickup. FoodFlow does the
dispatch: it picks the driver, splits the food across several organizations in one trip, routes it, tracks status,
and explains each decision. We should name specific apps only after checking what they actually do.

**Why would restaurants participate?**
Posting takes under a minute and pickup is handled for them. In the US, the Bill Emerson Good Samaritan Food
Donation Act gives liability protection to good faith food donors, and there are enhanced federal tax deductions
for donated food. Both are general context: [SOURCE NEEDED: verify current Good Samaritan Act scope and current tax
deduction rules with an official source] and restaurants should confirm with their own advisors.

**Food safety?**
The restaurant must confirm safe storage and handling before posting (the API rejects it otherwise), each rescue
has a pickup deadline and time sensitivity, and rescues expire automatically after the deadline. A real rollout would
add partner training, temperature logging and org side inspection on receipt.

**Where do drivers come from?**
Volunteers recruited through the organizations themselves, student groups and community partners. The demo uses
seeded drivers. Availability is one toggle, and an offer goes to one driver at a time.

**Why this algorithm?**
Rescues arrive one at a time and need an answer in seconds, so an online greedy match with a top-k prefilter is
fast and easy to explain. Batch mode is earliest deadline first. The Hungarian algorithm is the upgrade for
globally optimal batch assignment.

**Where does ML actually help?**
Forecasting which restaurants are likely to have surplus tonight so drivers can be staged nearby. Matching itself
is a transparent formula on purpose, because people need to trust and audit it. Today the model is a prototype on
synthetic data; it becomes useful once trained on partner history.

**Scaling?**
The prefilter is O(D log k + N log k); with PostGIS a KNN query on a GIST index makes it about O(log n). The schema
for that is in `backend/db/schema_postgres.sql`. Routing is cached.

**People without smartphones?**
They never need one. Organizations are the bridge: they post needs and distribute food. SMS and phone access
through organizations is roadmap phase 2.

**Fraud or misuse?**
Accounts have roles and every endpoint checks ownership. Impact counts only after the receiving organization
confirms. A real rollout would verify organizations (for example, nonprofit status) and restaurants before
activation.

**Sustainability and revenue?**
Free for organizations and drivers. Possible paths: city or county contracts, foundation grants, and an optional
paid tier for restaurant groups with reporting. [SOURCE NEEDED if we cite any market or funding figures.]

**More food than drivers?**
Unmatched rescues stay open, the admin sees them, batch matching retries earliest deadline first, and the
forecast lets coordinators recruit drivers before the evening rush.

**An organization no longer needs food?**
Needs have deadlines and are only matched while open and unfilled; an organization can let a need lapse. Meals
already promised to a pending match are counted so needs are never overfilled.

**Food about to expire?**
Urgency rises as the deadline approaches and weights ETA more heavily, and drivers who cannot arrive in time are
excluded. The seeded "expiring soon" rescue shows this in its reasons.

**Disaster response?**
The same pipeline works for shelters after a storm: organizations post needs, drivers are dispatched, and
simulation helps plan capacity. That is roadmap phase 6, and would need partnership with emergency management.

## Statistics to fill in

- [SOURCE NEEDED: amount or share of US food surplus that goes unsold or uneaten, ReFED]
- [SOURCE NEEDED: number or share of people in food insecure households in the US, USDA ERS]
- [SOURCE NEEDED: Miami-Dade or Florida food insecurity figure, Feeding America Map the Meal Gap]
- [SOURCE NEEDED: share of food waste from restaurants and food service, ReFED]
