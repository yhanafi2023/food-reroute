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

// ---------- community need (Census), from a073982; served by GET /community-need/areas when that backend exists ----------

export type NeedBucket = "low" | "moderate" | "high" | "very_high";

export interface CensusArea {
  geoid: string; name: string; poverty_rate: number; margin_of_error_pct: number; population: number;
  population_below_poverty: number; bucket: NeedBucket; bucket_label: string; community_need_score: number;
  geometry: { type: "Polygon" | "MultiPolygon"; coordinates: number[][][] | number[][][][] };
}

export interface CommunityNeedAreas {
  source: string; disclaimer: string;
  legend: { bucket: NeedBucket; label: string; poverty_rate_range: string }[];
  areas: CensusArea[];
}

// ---------- surplus log / prospects (unchanged: app/routes/prospects.py matches this shape) ----------

export type EvidenceStrength = "measured" | "documented_donation" | "marketplace_listing" | "none_found";

export interface SourceLink { label: string; url: string; checked: string; how: string }
export interface Evidence { type: EvidenceStrength; summary: string; url: string; source_name: string; checked: string; how: string }

export interface LogSummary {
  days_logged: number; days_needed: number; complete: boolean; period_start: string | null; period_end: string | null;
  total_surplus_meals: number; total_surplus_lbs: number; recoverable_meals: number; recoverable_days: number;
  already_channeled_meals: number; typical_ready_times: string[]; basis: string;
}

export type Disposition = "discarded" | "composted" | "donated" | "sold_discounted" | "staff_meal" | "no_surplus";

export interface LogEntry {
  id?: number; log_date: string; surplus_meals: number; surplus_lbs: number; safe_to_donate: boolean;
  disposition: Disposition; food_categories: string; ready_time: string; notes: string;
}

export interface SurplusLogPayload { entries: LogEntry[]; summary: LogSummary }

export interface Prospect {
  id: string; name: string; business_type: string; neighborhood: string; address: string; address_note: string | null;
  lat: number; lng: number; geocode_source: string;
  contact: { phone: string | null; email: string | null; website: string | null };
  hours: string | null; evidence_strength: EvidenceStrength; evidence_label: string; evidence: Evidence[];
  surplus_measurement: { meals: number; period: string; period_days: number; source: string; url: string } | null;
  pickup_frequency: string | null; existing_commitments: { program: string; detail: string; url: string }[];
  sources: SourceLink[]; miles_from_fiu: number; enrollment_status: "not_enrolled";
  log_summary?: LogSummary; log?: SurplusLogPayload;
}

export interface ProspectMeta {
  neighborhoods: string[]; business_types: string[]; evidence_levels: { value: EvidenceStrength; label: string }[];
  reference_point: { name: string; address: string; lat: number; lng: number; geocode_source: string };
  checked: string; about: string;
}

export interface Opportunity {
  rank: number; id: string; name: string; kind: "prospect" | "enrolled_partner"; is_demo: boolean;
  recoverable_meals_per_week: number; pickups_per_week: number | null; meals_per_pickup: number | null;
  already_channeled_meals_per_week: number; existing_commitments: string[]; basis: string; miles_from_fiu: number;
}

export interface Opportunities {
  ranked: Opportunity[];
  not_ranked: { id: string; name: string; kind: string; reason: string; evidence_strength: EvidenceStrength; miles_from_fiu: number }[];
  method: string;
}
