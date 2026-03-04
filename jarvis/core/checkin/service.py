"""GPS check-in business logic."""

import json
import math
from datetime import datetime

try:
    from zoneinfo import ZoneInfo
except ImportError:
    from backports.zoneinfo import ZoneInfo

from .repository import CheckinRepository

_RO_TZ = ZoneInfo('Europe/Bucharest')


def haversine(lat1, lon1, lat2, lon2):
    """Distance in meters between two (lat, lng) points."""
    R = 6_371_000  # Earth radius in meters
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class CheckinService:

    def __init__(self):
        self.repo = CheckinRepository()

    # ── Location CRUD ──

    def get_locations(self, active_only=True):
        return self.repo.get_active_locations() if active_only else self.repo.get_all_locations()

    def create_location(self, name, latitude, longitude, radius, created_by, allowed_ips=None, auto_checkout_radius=200):
        return self.repo.create_location(
            name, float(latitude), float(longitude), int(radius), allowed_ips or [],
            created_by, int(auto_checkout_radius),
        )

    def update_location(self, location_id, name, latitude, longitude, radius, is_active, allowed_ips=None, auto_checkout_radius=200):
        return self.repo.update_location(
            location_id, name, float(latitude), float(longitude), int(radius),
            allowed_ips or [], is_active, int(auto_checkout_radius),
        )

    def delete_location(self, location_id):
        return self.repo.delete_location(location_id)

    # ── Status ──

    def get_status(self, jarvis_user_id):
        """Today's punches and next expected direction for this user."""
        mapping = self.repo.get_biostar_user_id(jarvis_user_id)
        if not mapping:
            return {'mapped': False, 'punches': [], 'next_direction': 'IN'}

        biostar_uid = mapping['biostar_user_id']
        today = datetime.now(_RO_TZ).strftime('%Y-%m-%d')
        punches = self.repo.get_today_punches(biostar_uid, today)
        return {
            'mapped': True,
            'biostar_user_id': biostar_uid,
            'punches': _serialize_punches(punches),
            'next_direction': _next_direction(punches),
        }

    # ── Punch ──

    def punch(self, jarvis_user_id, lat=None, lng=None, direction=None, client_ip=None, qr_token=None):
        """Validate GPS, IP, or QR and insert punch. Returns dict with success/error."""
        # 1. Resolve user mapping
        mapping = self.repo.get_biostar_user_id(jarvis_user_id)
        if not mapping:
            return {'success': False, 'error': 'No BioStar employee mapping found. Contact HR.'}

        biostar_uid = mapping['biostar_user_id']

        # 2. Find matching location (GPS or IP fallback)
        locations = self.repo.get_active_locations()
        if not locations:
            return {'success': False, 'error': 'No check-in locations configured. Contact admin.'}

        matched_loc = None
        match_source = None
        match_dist = None

        # Try GPS first
        if lat is not None and lng is not None:
            nearest, nearest_dist = None, float('inf')
            for loc in locations:
                d = haversine(float(lat), float(lng), float(loc['latitude']), float(loc['longitude']))
                if d < nearest_dist:
                    nearest_dist, nearest = d, loc

            if nearest_dist <= nearest['allowed_radius_meters']:
                matched_loc = nearest
                match_source = 'gps_mobile'
                match_dist = round(nearest_dist, 1)

        # IP fallback if GPS didn't match or wasn't provided
        if not matched_loc and client_ip:
            matched_loc = _match_ip(locations, client_ip)
            if matched_loc:
                match_source = 'ip_wifi'
                match_dist = 0

        # QR code fallback — token format: "checkin:<location_id>"
        if not matched_loc and qr_token:
            matched_loc = _match_qr(locations, qr_token)
            if matched_loc:
                match_source = 'qr_code'
                match_dist = 0

        if not matched_loc:
            # Build error message depending on what we tried
            if lat is not None and lng is not None:
                return {
                    'success': False,
                    'error': f'Too far from {nearest["name"]} ({nearest_dist:.0f}m away, max {nearest["allowed_radius_meters"]}m)',
                    'distance': round(nearest_dist, 1),
                    'location': nearest['name'],
                    'allowed_radius': nearest['allowed_radius_meters'],
                }
            return {
                'success': False,
                'error': 'No GPS and your network is not recognized as an office network.',
            }

        # 3. Determine direction
        now = datetime.now(_RO_TZ)
        today = now.strftime('%Y-%m-%d')
        punches = self.repo.get_today_punches(biostar_uid, today)

        if direction and direction.upper() in ('IN', 'OUT'):
            actual_dir = direction.upper()
        else:
            actual_dir = _next_direction(punches)

        # 4. Insert
        event_id = f'gps-{biostar_uid}-{now.strftime("%Y%m%d%H%M%S")}'
        raw_data = json.dumps({
            'source': match_source,
            'latitude': float(lat) if lat is not None else None,
            'longitude': float(lng) if lng is not None else None,
            'client_ip': client_ip,
            'location_id': matched_loc['id'],
            'location_name': matched_loc['name'],
            'distance_meters': match_dist,
            'jarvis_user_id': jarvis_user_id,
        })

        result = self.repo.insert_gps_punch(
            biostar_event_id=event_id,
            biostar_user_id=biostar_uid,
            event_datetime=now.strftime('%Y-%m-%dT%H:%M:%S'),
            direction=actual_dir,
            raw_data_json=raw_data,
        )

        if not result:
            return {'success': False, 'error': 'Duplicate punch. Try again in a minute.'}

        return {
            'success': True,
            'direction': actual_dir,
            'time': now.strftime('%H:%M:%S'),
            'location': matched_loc['name'],
            'distance': match_dist,
            'method': match_source,
        }


def _match_qr(locations, qr_token):
    """Validate QR token format 'checkin:<location_id>' against active locations."""
    if not qr_token or ':' not in qr_token:
        return None
    prefix, loc_id_str = qr_token.split(':', 1)
    if prefix != 'checkin':
        return None
    try:
        loc_id = int(loc_id_str)
    except ValueError:
        return None
    for loc in locations:
        if loc['id'] == loc_id:
            return loc
    return None


def _match_ip(locations, client_ip):
    """Check if client_ip matches any location's allowed_ips list."""
    if not client_ip:
        return None
    for loc in locations:
        allowed = loc.get('allowed_ips') or []
        if isinstance(allowed, str):
            allowed = json.loads(allowed)
        if client_ip in allowed:
            return loc
    return None


def _next_direction(punches):
    """IN if no punches or last was OUT, else OUT."""
    if not punches:
        return 'IN'
    last = punches[-1]
    return 'OUT' if last.get('direction') == 'IN' else 'IN'


def _serialize_punches(punches):
    """Convert datetime objects to ISO strings for JSON."""
    serialized = []
    for p in punches:
        row = dict(p)
        if row.get('event_datetime') and hasattr(row['event_datetime'], 'isoformat'):
            row['event_datetime'] = row['event_datetime'].isoformat()
        serialized.append(row)
    return serialized
