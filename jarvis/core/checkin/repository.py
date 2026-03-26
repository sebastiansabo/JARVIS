"""GPS check-in data access layer."""

import json

from core.base_repository import BaseRepository


class CheckinRepository(BaseRepository):
    """CRUD for checkin_locations + GPS punch insertion."""

    # ── Location queries ──

    def get_active_locations(self):
        return self.query_all(
            "SELECT * FROM checkin_locations WHERE is_active = TRUE ORDER BY name"
        )

    def get_all_locations(self):
        return self.query_all("SELECT * FROM checkin_locations ORDER BY name")

    def get_location_by_id(self, location_id):
        return self.query_one(
            "SELECT * FROM checkin_locations WHERE id = %s", (location_id,)
        )

    def create_location(self, name, latitude, longitude, radius, allowed_ips, created_by, auto_checkout_radius=200):
        return self.execute(
            """INSERT INTO checkin_locations
                   (name, latitude, longitude, allowed_radius_meters, allowed_ips,
                    auto_checkout_radius_meters, created_by)
               VALUES (%s, %s, %s, %s, %s::jsonb, %s, %s) RETURNING *""",
            (name, latitude, longitude, radius, json.dumps(allowed_ips),
             auto_checkout_radius, created_by),
            returning=True,
        )

    def update_location(self, location_id, name, latitude, longitude, radius, allowed_ips, is_active, auto_checkout_radius=200):
        return self.execute(
            """UPDATE checkin_locations
               SET name = %s, latitude = %s, longitude = %s,
                   allowed_radius_meters = %s, allowed_ips = %s::jsonb,
                   is_active = %s, auto_checkout_radius_meters = %s,
                   updated_at = NOW()
               WHERE id = %s RETURNING *""",
            (name, latitude, longitude, radius, json.dumps(allowed_ips),
             is_active, auto_checkout_radius, location_id),
            returning=True,
        )

    def delete_location(self, location_id):
        return self.execute(
            "DELETE FROM checkin_locations WHERE id = %s", (location_id,)
        )

    # ── User mapping ──

    def get_biostar_user_id(self, jarvis_user_id):
        """Reverse-lookup: jarvis user_id -> biostar_user_id via biostar_employees."""
        return self.query_one(
            """SELECT biostar_user_id FROM biostar_employees
               WHERE mapped_jarvis_user_id = %s AND status = 'active'
               LIMIT 1""",
            (jarvis_user_id,),
        )

    # ── Punch queries ──

    def get_today_punches(self, biostar_user_id, date_str):
        """Get all punches for a user on a given date."""
        return self.query_all(
            """SELECT id, biostar_event_id, event_datetime, direction,
                      device_name, raw_data
               FROM biostar_punch_logs
               WHERE biostar_user_id = %s AND event_datetime::date = %s::date
               ORDER BY event_datetime ASC""",
            (biostar_user_id, date_str),
        )

    def insert_gps_punch(self, biostar_event_id, biostar_user_id, event_datetime,
                         direction, raw_data_json):
        """Insert a GPS-based punch into biostar_punch_logs."""
        return self.execute(
            """INSERT INTO biostar_punch_logs
                   (biostar_event_id, biostar_user_id, event_datetime,
                    event_type, direction, device_name, raw_data)
               VALUES (%s, %s, %s, 'GPS_CHECKIN', %s, 'GPS Mobile', %s)
               ON CONFLICT (biostar_event_id, (event_datetime::date)) DO NOTHING
               RETURNING id, biostar_event_id""",
            (biostar_event_id, biostar_user_id, event_datetime,
             direction, raw_data_json),
            returning=True,
        )
