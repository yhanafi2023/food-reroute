// Mirrors the real backend contract exactly (app/views.py, app/auth.py, app/routes/*.py).
// snake_case, ISO times in UTC ("...Z"). See backend/app/models.py for the source of truth.

export type Role = "restaurant_staff" | "restaurant_manager" | "volunteer" | "org_staff" | "org_manager" | "admin";
export const RESTAURANT_ROLES: Role[] = ["restaurant_staff", "restaurant_manager"];
export const ORG_ROLES: Role[] = ["org_staff", "org_manager"];

export type RescueStatus =
  | "posted" | "matched" | "en_route_pickup" | "picked_up" | "en_route_dropoff" | "delivered" | "received"
  | "cancelled" | "expired" | "rejected" | "reassigned";
export type TripStatus = RescueStatus;
export type TripMode = "volunteer" | "waymo_sim" | "robot_sim";
export type StopStatus = "pending" | "delivered" | "received" | "rejected" | "rerouted" | "cancelled";
export type FoodCategory = "hot" | "cold" | "frozen" | "shelf_stable";
export type FoodUnit = "individual_meal" | "bag" | "box" | "tray" | "half_pan" | "full_pan";

export interface User { id: number; email: string; name: string; first_name: string; role: Role; organization_id: number | null }
export interface AuthResponse { token: string; user: User }

// ---------- community need (Census) ----------

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

export interface OrgCommunityNeed {
  organization_id: number; name: string; community_need: Omit<CensusArea, "geometry"> & { source: string } | null;
  disclaimer: string;
  requested_food: { meals_committed_today: number; current_need: number | null; typical_nightly_need: number | null };
}

// ---------- matching / scoring ----------

export interface ScoreBreakdown {
  distance_score: number; urgency_score: number; demand_score: number; capacity_score: number;
  community_need_score: number; total: number;
  community_need: Omit<CensusArea, "geometry"> & { source: string } | null;
}

export interface EligibleOrg { organization_id: number; name: string; estimated_arrival: string | null; score: ScoreBreakdown; why: string[]; rank: number }
export interface IneligibleOrg { organization_id: number; name: string; reasons: { code: string; text: string }[]; groups: string[]; estimated_arrival: string | null }

export interface MatchingExplanation {
  rescue_id: number; attempt: number; status: RescueStatus; weights_used: "standard" | "community_need_priority";
  matching_weights: Record<string, number>;
  eligible: EligibleOrg[]; ineligible: IneligibleOrg[];
  trips: { id: number; mode: TripMode; simulated: boolean; mode_reason: string; status: TripStatus }[];
}

export interface MatchResult { matched: boolean; reason?: string; attempt?: number; trips?: number[]; estimated?: boolean }

// ---------- rescues / trips / stops ----------

export interface RestaurantRef { id: number; name: string; address: string; lat: number; lng: number }
export interface OrganizationRef { id: number; name: string; address: string; lat: number; lng: number }

export interface Carrier {
  type: "volunteer" | TripMode; simulated: boolean;
  first_name?: string; vehicle?: string; contact?: string; user_id?: number; email?: string;
  vehicle_id?: string; label?: string;
}

export interface Stop {
  id: number; seq: number; organization: OrganizationRef; allocated_meals: number; status: StopStatus;
  eta: string | null; delivered_at: string | null; received_at: string | null; received_meals: number | null;
  condition: "accepted" | "partially_accepted" | "rejected" | null; reject_reason: string | null;
  temperature_f: number | null; incomplete_fields: string[];
  receiving_instructions?: string; curb_location?: string; receiving_contact?: { name: string; phone: string } | null;
  dropoff_code?: string; received_by_name?: string; photo_url?: string; meals_served?: number | null;
}

export interface Trip {
  id: number; rescue_id: number; mode: TripMode; simulated: boolean; status: TripStatus;
  handoff_state: string | null; mode_reason: string; estimated: boolean; eta_pickup: string;
  load_deadline: string | null; unload_deadline: string | null; picked_up_meals: number | null;
  started_at: string | null; finished_at: string | null; carrier: Carrier; stops: Stop[];
}

export interface Rescue {
  id: number; status: RescueStatus; is_draft: boolean; is_fictional: boolean; restaurant: RestaurantRef;
  quantity: number; unit: FoodUnit; est_meals: number; meals_per_unit_assumption: number; category: FoodCategory;
  description: string; prepared_at: string | null; allergens: string[] | null; allergens_declared: boolean;
  dietary_tags: string[]; safe_until: string; pickup_deadline: string; pickup_instructions: string;
  attested_by: number | null; attested_at: string | null; duplicate_of: number | null; created_at: string;
  requeue_count: number; quantities: { posted_meals: number; picked_up_meals: number | null; received_meals: number | null };
  trips: Trip[];
  pickup_code?: string; cancel_reason?: string; fmv_per_meal?: number | null; cost_basis_per_meal?: number | null;
}

export interface QuickPostBody {
  quantity: number; unit: FoodUnit; category: FoodCategory; pickup_deadline: string; attested: boolean;
  description?: string; prepared_at?: string; allergens?: string[]; dietary_tags?: string[];
  pickup_instructions?: string; safe_until?: string; fmv_per_meal?: number; cost_basis_per_meal?: number;
}

export interface CreateRescueResponse { rescue: Rescue; warnings: string[]; matching: MatchResult }

// ---------- dashboards ----------

export interface Impact {
  meals_rescued: number; lbs_diverted: number; deliveries_completed: number; restaurants: number;
  organizations: number; avg_delivery_minutes: number; community_value_estimate_usd: number;
  includes_demo_data: boolean;
}

export interface VolunteerTrips { offers: Trip[]; active: Trip[]; history: Trip[] }
export interface OrgDeliveryItem { stop: Stop; rescue: Rescue }
export interface OrgDeliveries { incoming: OrgDeliveryItem[]; to_confirm: OrgDeliveryItem[]; history: OrgDeliveryItem[] }

export interface NetworkRestaurant { id: number; name: string; address: string; lat: number; lng: number; is_fictional: boolean }
export interface NetworkOrganization extends NetworkRestaurant {
  onboarding_complete: boolean; typical_nightly_need: number | null; current_need: number | null;
  community_need: Omit<CensusArea, "geometry"> & { source: string } | null;
}
export interface NetworkVolunteer {
  id: number; name: string; first_name: string; vehicle: string; capacity_meals: number; lat: number; lng: number;
  position_is_live: boolean; on_active_trip: boolean; available_now: boolean;
}

export interface AdminNetwork {
  restaurants: NetworkRestaurant[]; organizations: NetworkOrganization[]; volunteers: NetworkVolunteer[];
  active_rescues: Rescue[]; active_trips: Trip[];
  stats: { open_rescues: number; active_trips: number; available_volunteers: number; total_volunteers: number };
  impact: Impact;
}

export interface Assumption { value: unknown; kind: "assumption" | "cited"; note?: string; source?: string }
export type Assumptions = Record<string, Assumption>;

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
