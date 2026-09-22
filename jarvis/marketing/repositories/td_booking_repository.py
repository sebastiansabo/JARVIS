"""Repository for the public test-drive booking layer (mkt_td_* tables)."""
from core.base_repository import BaseRepository

_PAGE_COLS = {
    'project_id', 'company_id', 'event_id', 'slug', 'status', 'opens_at',
    'closes_at', 'min_lead_minutes', 'slot_minutes', 'buffer_minutes',
    'max_bookings_per_contact', 'access_code', 'title', 'intro', 'thank_you',
    'notify_user_ids', 'created_by',
}


class TdBookingRepository(BaseRepository):
    # ---- pages ----
    def create_page(self, data: dict) -> dict:
        fields = {k: v for k, v in data.items() if k in _PAGE_COLS}
        cols = ', '.join(fields)
        ph = ', '.join(['%s'] * len(fields))
        return self.execute(
            f'INSERT INTO mkt_td_booking_pages ({cols}) VALUES ({ph}) RETURNING *',
            tuple(fields.values()), returning=True)

    def get_page(self, page_id: int):
        return self.query_one('SELECT * FROM mkt_td_booking_pages WHERE id=%s', (page_id,))

    def get_page_by_slug(self, slug: str):
        return self.query_one(
            'SELECT * FROM mkt_td_booking_pages WHERE slug=%s AND deleted_at IS NULL', (slug,))

    def list_pages(self, company_id=None):
        if company_id:
            return self.query_all(
                'SELECT * FROM mkt_td_booking_pages WHERE company_id=%s AND deleted_at IS NULL '
                'ORDER BY created_at DESC', (company_id,))
        return self.query_all(
            'SELECT * FROM mkt_td_booking_pages WHERE deleted_at IS NULL ORDER BY created_at DESC')

    def update_page(self, page_id: int, data: dict):
        fields = {k: v for k, v in data.items() if k in _PAGE_COLS}
        if not fields:
            return self.get_page(page_id)
        sets = ', '.join(f'{k}=%s' for k in fields)
        return self.execute(
            f'UPDATE mkt_td_booking_pages SET {sets}, updated_at=NOW() WHERE id=%s RETURNING *',
            tuple(fields.values()) + (page_id,), returning=True)

    def set_page_status(self, page_id: int, status: str):
        return self.execute(
            'UPDATE mkt_td_booking_pages SET status=%s, updated_at=NOW() WHERE id=%s RETURNING *',
            (status, page_id), returning=True)

    # ---- cars ----
    def add_car(self, page_id, vin, vehicle_id=None, default_advisor_user_id=None, sort_order=0):
        return self.execute(
            'INSERT INTO mkt_td_booking_cars (page_id, vin, vehicle_id, default_advisor_user_id, sort_order) '
            'VALUES (%s,%s,%s,%s,%s) RETURNING *',
            (page_id, vin, vehicle_id, default_advisor_user_id, sort_order), returning=True)

    def list_cars(self, page_id):
        return self.query_all(
            'SELECT * FROM mkt_td_booking_cars WHERE page_id=%s AND is_active ORDER BY sort_order, id',
            (page_id,))

    def get_car(self, car_id):
        return self.query_one('SELECT * FROM mkt_td_booking_cars WHERE id=%s', (car_id,))

    def remove_car(self, car_id):
        return self.execute('UPDATE mkt_td_booking_cars SET is_active=FALSE WHERE id=%s', (car_id,))

    # ---- windows ----
    def add_window(self, page_id, window_date, start_time, end_time, slot_minutes=None):
        return self.execute(
            'INSERT INTO mkt_td_booking_windows (page_id, window_date, start_time, end_time, slot_minutes) '
            'VALUES (%s,%s,%s,%s,%s) RETURNING *',
            (page_id, window_date, start_time, end_time, slot_minutes), returning=True)

    def list_windows(self, page_id):
        return self.query_all(
            'SELECT * FROM mkt_td_booking_windows WHERE page_id=%s ORDER BY window_date, start_time',
            (page_id,))
