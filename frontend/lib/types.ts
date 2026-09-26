// Mirrors the backend contract objects exactly (snake_case, ISO times in UTC).

export type Role = "RESTAURANT" | "DRIVER" | "ORGANIZATION" | "ADMIN";
export type Level = "LOW" | "MEDIUM" | "HIGH";
export type RescueStatus =
  | "OPEN" | "MATCHED" | "ACCEPTED" | "PICKED_UP" | "DELIVERED" | "CONFIRMED" | "EXPIRED" | "CANCELLED";
export type DeliveryStatus =
  | "HEADING_TO_RESTAURANT" | "ARRIVED_AT_RESTAURANT" | "PICKED_UP" | "DELIVERING" | "DELIVERED" | "CONFIRMED";

export interface Location { lat: number; lng: number }

export interface User { id: number; name: string; email: string; role: Role }
export interface AuthResponse { token: string; user: User }

export interface Rescue {
  id: number; restaurant_id: number; restaurant_name: string; food_type: string; meals: number;
  weight_lbs: number; pickup_address: string; lat: number; lng: number; pickup_deadline: string;
  time_sensitivity: Level; description: string; status: RescueStatus; created_at?: string;
}

export interface Need {
  id: number; organization_id: number; organization_name: string; meals_needed: number;
  meals_fulfilled: number; preferred_food: string; deadline: string; priority: Level;
  status: "OPEN" | "FULFILLED"; lat?: number; lng?: number;
}

export interface Breakdown { distance: number; eta: number; urgency: number; demand_fit: number; priority: number }
export interface Candidate { driver_name: string; stops_summary: string; score: number; breakdown: Breakdown }

export interface Stop {
  need_id?: number; organization_id: number; name: string; lat: number; lng: number; meals: number; confirmed?: boolean;
}

export interface Match {
  id: number | null; rescue_id: number; driver: { id: number; name: string; lat: number; lng: number };
  stops: Stop[]; pickup_miles: number; dropoff_miles: number; eta_minutes: number; score: number;
  reasons: string[]; top_candidates: Candidate[]; status?: string;
}

export interface Route {
  geometry: [number, number][]; distance_miles: number; eta_minutes: number; source: "mapbox" | "osrm" | "offline";
}

export interface Delivery {
  id: number; rescue_id: number; match_id: number; driver_id: number; driver_name: string;
  driver_location: Location; status: DeliveryStatus; meals: number; weight_lbs: number; route: Route;
  restaurant: { id: number; name: string; lat: number; lng: number; address: string }; food_type: string;
  stops: Stop[]; status_history: { status: DeliveryStatus; at: string }[]; eta_minutes: number;
  accepted_at: string; delivered_at: string | null; is_demo_seed: boolean;
}

export interface Impact {
  meals_rescued: number; lbs_diverted: number; deliveries_completed: number; restaurants: number;
  organizations: number; avg_delivery_minutes: number; community_value_estimate_usd: number;
  includes_demo_data: boolean;
}

export interface Place { id: number; name: string; lat: number; lng: number; address?: string }
export interface Restaurant extends Place { food_category: string; seats: number }
export interface Driver extends Place { is_available: boolean; capacity_meals: number; vehicle: string }
export interface Organization extends Place { org_type: string }

export interface RescueDetail { rescue: Rescue; match: Match | null; delivery: Delivery | null }
export interface CreateRescueResponse { rescue: Rescue; match: Match | null }

export interface RestaurantDashboard {
  restaurant: Restaurant;
  stats: { active: number; completed: number; meals_donated: number; lbs_diverted: number };
  rescues: RescueDetail[];
}

export interface DriverDashboard {
  driver: Driver; offer: { rescue: Rescue; match: Match } | null; active_delivery: Delivery | null;
  completed: Delivery[]; total_meals_moved: number;
}

export interface IncomingDelivery {
  delivery: Delivery; my_meals: number; my_stop_number: number; confirmed: boolean; can_confirm: boolean;
}

export interface OrganizationDashboard {
  organization: Organization; needs: Need[]; incoming: IncomingDelivery[]; received: IncomingDelivery[];
  meals_received: number;
}

export interface Network {
  restaurants: Restaurant[]; drivers: Driver[]; organizations: Organization[]; needs: Need[];
  rescues: RescueDetail[]; deliveries: Delivery[];
  stats: { open_rescues: number; active_deliveries: number; available_drivers: number; open_needs: number };
  impact: Impact;
}

export interface ForecastRow { restaurant: string; probability: number }
export interface Forecast { forecast: ForecastRow[]; label: string }
export interface ModelInfo {
  model_name: string; roc_auc: number; roc_auc_by_model: Record<string, number>; accuracy: number;
  n_train: number; n_test: number; test_period_start: string; features: string[]; trained_at: string;
  data: string; note: string;
}

export type SimEvent =
  | { t_ms: number; clock: string; type: "rescue_posted"; rescue: { id: number; restaurant_name: string; meals: number; lat: number; lng: number; food_type: string; pickup_deadline: string } }
  | { t_ms: number; clock: string; type: "matched"; rescue_id: number; driver: { id: number; name: string; lat: number; lng: number }; stops: Stop[]; route: Route; reasons: string[]; eta_minutes: number; duration_ms: number }
  | { t_ms: number; clock: string; type: "delivered"; rescue_id: number; driver_id: number; restaurant_name: string; meals: number; stops: { name: string; meals: number }[]; minutes: number; impact: { meals_rescued: number; lbs_diverted: number; deliveries_completed: number } }
  | { t_ms: number; clock: string; type: "unmatched"; rescue_id: number; reason: string };

export interface Simulation {
  label: string; seed: number; duration_ms: number; start_clock: string; end_clock: string; events: SimEvent[];
  summary: { meals_rescued: number; lbs_diverted: number; deliveries_completed: number; restaurants: number; organizations: number; rescues_posted: number };
}
