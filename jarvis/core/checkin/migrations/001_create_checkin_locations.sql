-- GPS Check-in Locations
-- Preset office locations for GPS-based mobile check-in validation

CREATE TABLE IF NOT EXISTS checkin_locations (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    latitude NUMERIC(10,7) NOT NULL,
    longitude NUMERIC(10,7) NOT NULL,
    allowed_radius_meters INTEGER NOT NULL DEFAULT 50,
    allowed_ips JSONB NOT NULL DEFAULT '[]'::JSONB,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_by INTEGER REFERENCES users(id) ON DELETE SET NULL,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_checkin_locations_active ON checkin_locations(is_active);
