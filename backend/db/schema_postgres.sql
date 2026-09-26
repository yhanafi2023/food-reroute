-- FoodFlow production schema: Postgres + PostGIS. Same tables as app/models.py,
-- with geography columns and GIST indexes so "nearest drivers / needs" becomes an
-- index backed KNN query (ORDER BY location <-> point LIMIT k), O(log n) instead
-- of scanning every row.
CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE users (
  id            BIGSERIAL PRIMARY KEY,
  name          VARCHAR(120) NOT NULL,
  email         VARCHAR(255) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role          VARCHAR(20)  NOT NULL CHECK (role IN ('RESTAURANT','DRIVER','ORGANIZATION','ADMIN')),
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT now()
);

CREATE TABLE restaurants (
  id                BIGSERIAL PRIMARY KEY,
  user_id           BIGINT UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  name              VARCHAR(120) NOT NULL,
  address           VARCHAR(255) NOT NULL DEFAULT '',
  location          GEOGRAPHY(POINT, 4326) NOT NULL,
  food_category     VARCHAR(40)  NOT NULL DEFAULT 'cuban',
  seats             INT          NOT NULL DEFAULT 80,
  hist_surplus_rate REAL         NOT NULL DEFAULT 0.3
);
CREATE INDEX ix_restaurants_location ON restaurants USING GIST (location);

CREATE TABLE drivers (
  id             BIGSERIAL PRIMARY KEY,
  user_id        BIGINT UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  name           VARCHAR(120) NOT NULL,
  location       GEOGRAPHY(POINT, 4326) NOT NULL,
  is_available   BOOLEAN NOT NULL DEFAULT TRUE,
  capacity_meals INT     NOT NULL DEFAULT 80 CHECK (capacity_meals > 0),
  vehicle        VARCHAR(60) NOT NULL DEFAULT 'Car'
);
-- Partial GIST index: only available drivers are ever searched by distance.
CREATE INDEX ix_drivers_available_location ON drivers USING GIST (location) WHERE is_available;

CREATE TABLE organizations (
  id       BIGSERIAL PRIMARY KEY,
  user_id  BIGINT UNIQUE REFERENCES users(id) ON DELETE CASCADE,
  name     VARCHAR(120) NOT NULL,
  org_type VARCHAR(40)  NOT NULL DEFAULT 'Food bank',
  address  VARCHAR(255) NOT NULL DEFAULT '',
  location GEOGRAPHY(POINT, 4326) NOT NULL
);
CREATE INDEX ix_organizations_location ON organizations USING GIST (location);

CREATE TABLE food_needs (
  id              BIGSERIAL PRIMARY KEY,
  organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  meals_needed    INT NOT NULL CHECK (meals_needed > 0),
  meals_fulfilled INT NOT NULL DEFAULT 0 CHECK (meals_fulfilled >= 0),
  preferred_food  VARCHAR(120) NOT NULL DEFAULT 'Any',
  deadline        TIMESTAMPTZ NOT NULL,
  priority        VARCHAR(10) NOT NULL CHECK (priority IN ('LOW','MEDIUM','HIGH')),
  status          VARCHAR(10) NOT NULL DEFAULT 'OPEN' CHECK (status IN ('OPEN','FULFILLED')),
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Open needs, soonest deadline first (matching input, org dashboards).
CREATE INDEX ix_needs_open_deadline ON food_needs (deadline) WHERE status = 'OPEN';
CREATE INDEX ix_needs_organization ON food_needs (organization_id);

CREATE TABLE food_rescues (
  id               BIGSERIAL PRIMARY KEY,
  restaurant_id    BIGINT NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  food_type        VARCHAR(120) NOT NULL,
  meals            INT  NOT NULL CHECK (meals > 0),
  weight_lbs       REAL NOT NULL DEFAULT 0 CHECK (weight_lbs >= 0),
  pickup_address   VARCHAR(255) NOT NULL DEFAULT '',
  location         GEOGRAPHY(POINT, 4326) NOT NULL,
  pickup_deadline  TIMESTAMPTZ NOT NULL,
  time_sensitivity VARCHAR(10) NOT NULL CHECK (time_sensitivity IN ('LOW','MEDIUM','HIGH')),
  description      TEXT NOT NULL DEFAULT '',
  status           VARCHAR(12) NOT NULL DEFAULT 'OPEN'
                   CHECK (status IN ('OPEN','MATCHED','ACCEPTED','PICKED_UP','DELIVERED','CONFIRMED','EXPIRED','CANCELLED')),
  is_demo_seed     BOOLEAN NOT NULL DEFAULT FALSE,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Batch matching and the expiry sweep read rescues by status, earliest deadline first.
CREATE INDEX ix_rescues_status_deadline ON food_rescues (status, pickup_deadline);
CREATE INDEX ix_rescues_restaurant ON food_rescues (restaurant_id);

CREATE TABLE matches (
  id             BIGSERIAL PRIMARY KEY,
  rescue_id      BIGINT NOT NULL REFERENCES food_rescues(id) ON DELETE CASCADE,
  driver_id      BIGINT NOT NULL REFERENCES drivers(id) ON DELETE CASCADE,
  pickup_miles   REAL NOT NULL,
  dropoff_miles  REAL NOT NULL,
  eta_minutes    REAL NOT NULL,
  score          REAL NOT NULL,
  reasons        JSONB NOT NULL DEFAULT '[]',
  top_candidates JSONB NOT NULL DEFAULT '[]',
  status         VARCHAR(12) NOT NULL DEFAULT 'PENDING' CHECK (status IN ('PENDING','ACCEPTED','DECLINED','SUPERSEDED')),
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_matches_rescue ON matches (rescue_id);
-- A driver's pending offer.
CREATE INDEX ix_matches_driver_status ON matches (driver_id, status);

CREATE TABLE match_stops (
  id              BIGSERIAL PRIMARY KEY,
  match_id        BIGINT NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
  need_id         BIGINT NOT NULL REFERENCES food_needs(id) ON DELETE CASCADE,
  organization_id BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  seq             INT NOT NULL,
  meals           INT NOT NULL CHECK (meals > 0),
  confirmed_at    TIMESTAMPTZ
);
CREATE INDEX ix_match_stops_match ON match_stops (match_id);
-- Deliveries by organization: an org's incoming and received drop offs.
CREATE INDEX ix_match_stops_org ON match_stops (organization_id, confirmed_at);

CREATE TABLE deliveries (
  id             BIGSERIAL PRIMARY KEY,
  rescue_id      BIGINT NOT NULL UNIQUE REFERENCES food_rescues(id) ON DELETE CASCADE,
  match_id       BIGINT NOT NULL UNIQUE REFERENCES matches(id) ON DELETE CASCADE,
  driver_id      BIGINT NOT NULL REFERENCES drivers(id) ON DELETE CASCADE,
  status         VARCHAR(24) NOT NULL DEFAULT 'HEADING_TO_RESTAURANT'
                 CHECK (status IN ('HEADING_TO_RESTAURANT','ARRIVED_AT_RESTAURANT','PICKED_UP','DELIVERING','DELIVERED','CONFIRMED')),
  meals          INT  NOT NULL,
  weight_lbs     REAL NOT NULL DEFAULT 0,
  route          JSONB NOT NULL,
  status_history JSONB NOT NULL DEFAULT '[]',
  accepted_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  delivered_at   TIMESTAMPTZ,
  is_demo_seed   BOOLEAN NOT NULL DEFAULT FALSE
);
-- Deliveries by driver: the driver's active delivery and history.
CREATE INDEX ix_deliveries_driver_status ON deliveries (driver_id, status);

CREATE TABLE impact_events (
  id               BIGSERIAL PRIMARY KEY,
  delivery_id      BIGINT NOT NULL REFERENCES deliveries(id) ON DELETE CASCADE,
  restaurant_id    BIGINT NOT NULL REFERENCES restaurants(id) ON DELETE CASCADE,
  organization_id  BIGINT NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  meals            INT  NOT NULL CHECK (meals > 0),
  weight_lbs       REAL NOT NULL DEFAULT 0,
  delivery_minutes REAL NOT NULL DEFAULT 0,
  is_demo_seed     BOOLEAN NOT NULL DEFAULT FALSE,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX ix_impact_events_delivery ON impact_events (delivery_id);

-- Example KNN prefilter (the 5 nearest available drivers to a pickup):
--   SELECT id, name, ST_Distance(location, ST_MakePoint(:lng, :lat)::geography) / 1609.344 AS miles
--   FROM drivers WHERE is_available AND capacity_meals >= :meals
--   ORDER BY location <-> ST_MakePoint(:lng, :lat)::geography LIMIT 5;
