// Shapes returned by the FoodFlow API (backend/app/views.py and routes). Times are ISO UTC strings.

export type Role = "restaurant_staff" | "restaurant_manager" | "volunteer" | "org_staff" | "org_manager" | "admin";
export type Workspace = "restaurant" | "volunteer" | "org" | "coordinator";

export interface User {
  id: number;
  email: string;
  name: string;
  first_name: string;
  role: Role;
  organization_id: number | null;
}

export interface AuthResponse {
  token: string;
  user: User;
}

export type RescueStatus =
  | "posted"
  | "matched"
  | "en_route_pickup"
  | "picked_up"
  | "en_route_dropoff"
  | "delivered"
  | "received"
  | "rejected"
  | "expired"
  | "cancelled";

export type TripStatus =
  | "matched"
  | "en_route_pickup"
  | "picked_up"
  | "en_route_dropoff"
  | "delivered"
  | "received"
  | "rejected"
  | "cancelled"
  | "reassigned"
  | "expired";

export type StopStatus = "pending" | "delivered" | "received" | "rejected" | "rerouted" | "cancelled";

export interface Place {
  id: number;
  name: string;
  address: string;
  lat: number;
  lng: number;
}

export interface Carrier {
  type: "volunteer" | "waymo_sim" | "robot_sim";
  simulated: boolean;
  first_name?: string;
  vehicle?: string;
  contact?: string;
  vehicle_id?: string | null;
  label?: string;
}

export interface Stop {
  id: number;
  seq: number;
  organization: Place;
  allocated_meals: number;
  status: StopStatus;
  eta: string | null;
  delivered_at: string | null;
  received_at: string | null;
  received_meals: number | null;
  condition: string | null;
  reject_reason: string | null;
  temperature_f: number | null;
  incomplete_fields: string[] | null;
  receiving_instructions?: string;
  curb_location?: string;
  receiving_contact?: { name: string; phone: string } | null;
  dropoff_code?: string;
  received_by_name?: string;
}

export interface Trip {
  id: number;
  rescue_id: number;
  mode: "volunteer" | "waymo_sim" | "robot_sim";
  simulated: boolean;
  status: TripStatus;
  handoff_state: string | null;
  mode_reason: string;
  estimated: boolean;
  eta_pickup: string | null;
  load_deadline: string | null;
  unload_deadline: string | null;
  picked_up_meals: number | null;
  started_at: string | null;
  finished_at: string | null;
  carrier: Carrier;
  stops: Stop[];
}

export interface Rescue {
  id: number;
  status: RescueStatus;
  is_draft: boolean;
  is_fictional: boolean;
  restaurant: Place;
  quantity: number;
  unit: string;
  est_meals: number;
  category: string;
  description: string;
  safe_until: string | null;
  pickup_deadline: string;
  pickup_instructions: string | null;
  created_at: string;
  requeue_count: number;
  quantities: { posted_meals: number; picked_up_meals: number | null; received_meals: number | null };
  trips: Trip[];
  pickup_code?: string;
  cancel_reason?: string | null;
}

export interface PostResult {
  rescue: Rescue;
  warnings: string[];
  matching: { matched: boolean; attempt: number; trips: number[]; estimated: boolean; reason?: string };
}

export interface VolunteerTrips {
  offers: Trip[];
  active: Trip[];
  history: Trip[];
}

export interface OrgDelivery {
  stop: Stop;
  rescue: Rescue;
}

export interface OrgDeliveries {
  incoming: OrgDelivery[];
  to_confirm: OrgDelivery[];
  history: OrgDelivery[];
}

export interface DemoState {
  demo_clock: boolean;
  running: boolean;
  rate: number;
  now: string;
  local_time: string;
  start_local: string | null;
  label: string;
}

export interface MatchingExplanation {
  rescue_id: number;
  attempt: number | null;
  status: string;
  eligible: { organization_id: number; name: string; estimated_arrival: string | null }[];
  ineligible: { organization_id: number; name: string; reasons: { code: string; text: string }[]; groups: string[]; estimated_arrival: string | null }[];
  trips: { id: number; mode: string; simulated: boolean; mode_reason: string; status: string }[];
}
