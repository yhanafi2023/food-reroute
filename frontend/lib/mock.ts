// Contract shaped mock backend, enabled with NEXT_PUBLIC_USE_MOCKS=true.
// In memory and per tab: enough to click through every screen without the API.
import type {
  Delivery, DeliveryStatus, DriverDashboard, Impact, Match, Network, Need, OrganizationDashboard, Rescue,
  RestaurantDashboard, Role, Simulation, User,
} from "./types";

const ABC = { id: 1, name: "ABC Restaurant", lat: 25.7635, lng: -80.368, address: "10780 SW 8th St, Miami, FL", food_category: "cuban", seats: 90 };
const MARCUS = { id: 1, name: "Marcus", lat: 25.758, lng: -80.372, is_available: true, capacity_meals: 80, vehicle: "SUV" };
const FOOD_BANK = { id: 1, name: "Community Food Bank", lat: 25.748, lng: -80.35, org_type: "Food bank", address: "9800 SW 24th St, Miami, FL" };
const SHELTER = { id: 2, name: "Hope Shelter", lat: 25.77, lng: -80.355, org_type: "Shelter", address: "9900 W Flagler St, Miami, FL" };

const USERS: Record<string, User> = {
  "restaurant@demo.com": { id: 1, name: "ABC Restaurant", email: "restaurant@demo.com", role: "RESTAURANT" },
  "driver@demo.com": { id: 2, name: "Marcus", email: "driver@demo.com", role: "DRIVER" },
  "org@demo.com": { id: 3, name: "Community Food Bank", email: "org@demo.com", role: "ORGANIZATION" },
  "admin@demo.com": { id: 4, name: "FoodFlow Admin", email: "admin@demo.com", role: "ADMIN" },
};

const state: { user: User | null; rescue: Rescue | null; match: Match | null; delivery: Delivery | null; impact: Impact } = {
  user: null,
  rescue: null,
  match: null,
  delivery: null,
  impact: {
    meals_rescued: 87, lbs_diverted: 94.5, deliveries_completed: 3, restaurants: 3, organizations: 3,
    avg_delivery_minutes: 26.3, community_value_estimate_usd: 261, includes_demo_data: true,
  },
};

const iso = (minutesFromNow: number) => new Date(Date.now() + minutesFromNow * 60000).toISOString();

function needs(): Need[] {
  const confirmed = state.delivery?.status === "CONFIRMED";
  return [
    { id: 1, organization_id: 1, organization_name: FOOD_BANK.name, meals_needed: 30, meals_fulfilled: confirmed ? 30 : 0, preferred_food: "Any", deadline: iso(360), priority: "HIGH", status: confirmed ? "FULFILLED" : "OPEN", lat: FOOD_BANK.lat, lng: FOOD_BANK.lng },
    { id: 2, organization_id: 2, organization_name: SHELTER.name, meals_needed: 20, meals_fulfilled: confirmed ? 20 : 0, preferred_food: "Hot meals", deadline: iso(360), priority: "MEDIUM", status: confirmed ? "FULFILLED" : "OPEN", lat: SHELTER.lat, lng: SHELTER.lng },
  ];
}

function makeMatch(rescue: Rescue): Match {
  return {
    id: 1, rescue_id: rescue.id, driver: { id: 1, name: "Marcus", lat: MARCUS.lat, lng: MARCUS.lng },
    stops: [
      { need_id: 1, organization_id: 1, name: FOOD_BANK.name, lat: FOOD_BANK.lat, lng: FOOD_BANK.lng, meals: 30 },
      { need_id: 2, organization_id: 2, name: SHELTER.name, lat: SHELTER.lat, lng: SHELTER.lng, meals: 20 },
    ],
    pickup_miles: 0.64, dropoff_miles: 4.4, eta_minutes: 31.7, score: 4.1,
    reasons: [
      "Marcus is 0.6 mi away, the closest available driver",
      "Splits 50 meals across 2 organizations so every meal meets a real need",
      "Community Food Bank has a HIGH priority need and gets 30 meals",
      "Total trip 5.0 mi, about 32 min door to door",
    ],
    top_candidates: [
      { driver_name: "Marcus", stops_summary: "30 meals to Community Food Bank, then 20 meals to Hope Shelter", score: 4.1, breakdown: { distance: 5.04, eta: 3.17, urgency: 0, demand_fit: -3, priority: -1.6 } },
      { driver_name: "Aisha", stops_summary: "30 meals to Community Food Bank, then 20 meals to Hope Shelter", score: 5.9, breakdown: { distance: 6.2, eta: 3.9, urgency: 0, demand_fit: -3, priority: -1.6 } },
      { driver_name: "Diego", stops_summary: "30 meals to Community Food Bank, then 20 meals to Hope Shelter", score: 7.2, breakdown: { distance: 7.1, eta: 4.3, urgency: 0.4, demand_fit: -3, priority: -1.6 } },
    ],
    status: "PENDING",
  };
}

function makeDelivery(rescue: Rescue, match: Match): Delivery {
  return {
    id: 1, rescue_id: rescue.id, match_id: 1, driver_id: 1, driver_name: "Marcus", driver_location: { lat: MARCUS.lat, lng: MARCUS.lng },
    status: "HEADING_TO_RESTAURANT", meals: rescue.meals, weight_lbs: rescue.weight_lbs,
    route: { geometry: [[MARCUS.lat, MARCUS.lng], [ABC.lat, ABC.lng], [FOOD_BANK.lat, FOOD_BANK.lng], [SHELTER.lat, SHELTER.lng]], distance_miles: 5.0, eta_minutes: 31.7, source: "offline" },
    restaurant: { id: ABC.id, name: ABC.name, lat: ABC.lat, lng: ABC.lng, address: ABC.address }, food_type: rescue.food_type,
    stops: match.stops.map((s) => ({ ...s, confirmed: false })),
    status_history: [{ status: "HEADING_TO_RESTAURANT", at: new Date().toISOString() }], eta_minutes: 31.7,
    accepted_at: new Date().toISOString(), delivered_at: null, is_demo_seed: false,
  };
}

function detail() {
  return state.rescue ? [{ rescue: state.rescue, match: state.match, delivery: state.delivery }] : [];
}

function simulation(): Simulation {
  const route = { geometry: [[MARCUS.lat, MARCUS.lng], [ABC.lat, ABC.lng], [FOOD_BANK.lat, FOOD_BANK.lng], [SHELTER.lat, SHELTER.lng]] as [number, number][], distance_miles: 5, eta_minutes: 32, source: "offline" as const };
  return {
    label: "Simulated data", seed: 2026, duration_ms: 12000, start_clock: "6:00 PM", end_clock: "10:00 PM",
    events: [
      { t_ms: 500, clock: "6:05 PM", type: "rescue_posted", rescue: { id: 1, restaurant_name: ABC.name, meals: 50, lat: ABC.lat, lng: ABC.lng, food_type: "Rice and beans", pickup_deadline: iso(200) } },
      { t_ms: 1000, clock: "6:07 PM", type: "matched", rescue_id: 1, driver: { id: 1, name: "Marcus", lat: MARCUS.lat, lng: MARCUS.lng }, stops: makeMatch({ id: 1 } as Rescue).stops, route, reasons: ["Marcus is 0.6 mi away"], eta_minutes: 32, duration_ms: 8000 },
      { t_ms: 9000, clock: "6:39 PM", type: "delivered", rescue_id: 1, driver_id: 1, restaurant_name: ABC.name, meals: 50, stops: [{ name: FOOD_BANK.name, meals: 30 }, { name: SHELTER.name, meals: 20 }], minutes: 32, impact: { meals_rescued: 50, lbs_diverted: 60, deliveries_completed: 1 } },
    ],
    summary: { meals_rescued: 50, lbs_diverted: 60, deliveries_completed: 1, restaurants: 1, organizations: 2, rescues_posted: 1 },
  };
}

const ORDER: DeliveryStatus[] = ["HEADING_TO_RESTAURANT", "ARRIVED_AT_RESTAURANT", "PICKED_UP", "DELIVERING", "DELIVERED", "CONFIRMED"];

function handle(method: string, path: string, body: Record<string, unknown>): unknown {
  const route = `${method} ${path.replace(/\d+/g, ":id")}`;
  switch (route) {
    case "POST /auth/login":
    case "POST /auth/signup": {
      const email = String(body.email ?? "");
      const user = USERS[email] ?? { id: 9, name: String(body.name ?? "New user"), email, role: (body.role as Role) ?? "RESTAURANT" };
      state.user = user;
      return { token: `mock-${user.role}`, user };
    }
    case "GET /auth/me":
      if (!state.user) throw new Error("Please log in");
      return state.user;
    case "POST /rescues": {
      state.rescue = {
        id: 1, restaurant_id: 1, restaurant_name: ABC.name, food_type: String(body.food_type), meals: Number(body.meals),
        weight_lbs: Number(body.weight_lbs), pickup_address: ABC.address, lat: ABC.lat, lng: ABC.lng,
        pickup_deadline: String(body.pickup_deadline), time_sensitivity: body.time_sensitivity as Rescue["time_sensitivity"],
        description: String(body.description ?? ""), status: "MATCHED",
      };
      state.match = makeMatch(state.rescue);
      state.delivery = null;
      return { rescue: state.rescue, match: state.match };
    }
    case "POST /rescues/:id/accept":
      if (!state.rescue || !state.match) throw new Error("This rescue is not offered to you right now");
      state.delivery = makeDelivery(state.rescue, state.match);
      state.rescue.status = "ACCEPTED";
      return state.delivery;
    case "POST /rescues/:id/decline":
      state.rescue = null;
      state.match = null;
      return { rescue: null, match: null };
    case "PATCH /deliveries/:id/status": {
      const d = state.delivery;
      if (!d) throw new Error("Delivery not found");
      const next = ORDER[ORDER.indexOf(d.status) + 1];
      if (body.status !== next) throw new Error(`Cannot go from ${d.status} to ${String(body.status)}; the next step is ${next}`);
      d.status = next;
      d.status_history = [...d.status_history, { status: next, at: new Date().toISOString() }];
      return d;
    }
    case "POST /deliveries/:id/confirm": {
      const d = state.delivery;
      if (!d || d.status !== "DELIVERED") throw new Error("The driver has not marked this delivery as delivered yet");
      d.stops = d.stops.map((s) => ({ ...s, confirmed: true }));
      d.status = "CONFIRMED";
      d.status_history = [...d.status_history, { status: "CONFIRMED", at: new Date().toISOString() }];
      if (state.rescue) state.rescue.status = "CONFIRMED";
      state.impact = { ...state.impact, meals_rescued: state.impact.meals_rescued + d.meals, deliveries_completed: state.impact.deliveries_completed + 1 };
      return d;
    }
    case "GET /restaurants/dashboard": {
      const done = state.rescue?.status === "CONFIRMED";
      const dash: RestaurantDashboard = {
        restaurant: ABC,
        stats: { active: state.rescue && !done ? 1 : 0, completed: done ? 1 : 0, meals_donated: done ? state.rescue!.meals : 0, lbs_diverted: done ? state.rescue!.weight_lbs : 0 },
        rescues: detail(),
      };
      return dash;
    }
    case "GET /drivers/dashboard": {
      const active = state.delivery && !["DELIVERED", "CONFIRMED"].includes(state.delivery.status) ? state.delivery : null;
      const dash: DriverDashboard = {
        driver: { ...MARCUS, is_available: !active },
        offer: state.match && !state.delivery && state.rescue ? { rescue: state.rescue, match: state.match } : null,
        active_delivery: active,
        completed: state.delivery && !active ? [state.delivery] : [],
        total_meals_moved: state.delivery && !active ? state.delivery.meals : 0,
      };
      return dash;
    }
    case "PATCH /drivers/me/availability":
      return { ...MARCUS, is_available: Boolean(body.is_available) };
    case "GET /organizations/dashboard": {
      const d = state.delivery;
      const item = d ? { delivery: d, my_meals: 30, my_stop_number: 1, confirmed: d.status === "CONFIRMED", can_confirm: d.status === "DELIVERED" } : null;
      const dash: OrganizationDashboard = {
        organization: FOOD_BANK, needs: needs().filter((n) => n.organization_id === 1),
        incoming: item && !item.confirmed ? [item] : [], received: item?.confirmed ? [item] : [],
        meals_received: item?.confirmed ? 30 : 0,
      };
      return dash;
    }
    case "POST /organizations/needs":
      return { ...needs()[0], id: 3, meals_needed: Number(body.meals_needed), priority: body.priority, deadline: body.deadline };
    case "GET /organizations/needs":
      return needs();
    case "GET /admin/network": {
      const net: Network = {
        restaurants: [ABC], drivers: [MARCUS], organizations: [FOOD_BANK, SHELTER], needs: needs(), rescues: detail(),
        deliveries: state.delivery && state.delivery.status !== "CONFIRMED" ? [state.delivery] : [],
        stats: { open_rescues: state.rescue?.status === "MATCHED" ? 1 : 0, active_deliveries: state.delivery ? 1 : 0, available_drivers: 1, open_needs: 2 },
        impact: state.impact,
      };
      return net;
    }
    case "POST /matching/run":
      return { matched: 0, matches: [] };
    case "POST /simulation/run":
      return simulation();
    case "GET /ml/forecast":
      return { forecast: [{ restaurant: "Bayside Buffet", probability: 0.88 }, { restaurant: ABC.name, probability: 0.68 }], label: "Prototype model, synthetic training data" };
    case "GET /ml/info":
      return { model_name: "GradientBoostingClassifier", roc_auc: 0.87, roc_auc_by_model: { LogisticRegression: 0.868, GradientBoostingClassifier: 0.87 }, accuracy: 0.79, n_train: 10800, n_test: 2160, test_period_start: "2026-06-04", features: [], trained_at: "", data: "prototype trained on synthetic data", note: "Prototype model, synthetic training data." };
    case "GET /impact":
      return state.impact;
    case "POST /demo/reset":
      state.rescue = null;
      state.match = null;
      state.delivery = null;
      return { ok: true, message: "Demo data restored" };
    default:
      throw new Error(`Mock has no handler for ${method} ${path}`);
  }
}

export async function mockRequest<T>(method: string, path: string, body: unknown): Promise<T> {
  await new Promise((r) => setTimeout(r, 150));
  return structuredClone(handle(method, path.split("?")[0], (body ?? {}) as Record<string, unknown>)) as T;
}
