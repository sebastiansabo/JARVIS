-- Auto-checkout geofence radius
-- When a checked-in user moves beyond this distance from the location, auto check-out triggers.

ALTER TABLE checkin_locations
    ADD COLUMN IF NOT EXISTS auto_checkout_radius_meters INTEGER NOT NULL DEFAULT 200;
