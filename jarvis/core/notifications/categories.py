"""Canonical notification category registry.

Single source of truth for notification categories: which slugs exist, their
Romanian display names, push priority / Android channel, whether they are
mandatory (always delivered, un-mutable, bypass all gates), and the default
per-channel posture applied when a user has no explicit preference.

Pure data + helpers only — NO database or app imports, so this module is safe to
import from anywhere (migrations, gate helpers, routes) without tripping the
init-on-import circular import.

Locked defaults (2026-11-25):
  - most categories: in-app + push ON, email + SMS OFF (opt-in)
  - 'allocation' (migrated from users.notify_on_allocation): email-only, ON
  - mandatory ('approvals', 'system'): all channels ON (and forced at resolution)
"""

# The four delivery channels, in display order.
CHANNELS = ('in_app', 'push', 'email', 'sms')

# Always delivered on every channel; the user cannot mute these and they bypass
# the admin gates (kill-switch / is_active / quiet hours / rate limits). See the
# push gate and the shared preference filter.
MANDATORY_CATEGORIES = frozenset({'approvals', 'system'})

# Legacy prod slugs that don't match what the code emits. The registry backfill
# renames these (preserving row id + admin-tuned settings) so their settings and
# per-user preferences finally bind.
LEGACY_SLUG_RENAMES = {
    'approval': 'approvals',
    'attendance': 'hr_attendance',
    'message': 'chat',
}

# Default per-channel posture templates.
_ALL_ON = {'in_app': True, 'push': True, 'email': True, 'sms': True}
_STANDARD = {'in_app': True, 'push': True, 'email': False, 'sms': False}
_EMAIL_ONLY = {'in_app': False, 'push': False, 'email': True, 'sms': False}

# slug -> metadata. 'defaults' omitted means _STANDARD (in-app+push on, rest off).
CATEGORY_REGISTRY = {
    # Mandatory / operational
    'system':            {'name': 'Sistem',                 'priority': 'critical', 'android_channel_id': 'system_notifications',   'defaults': _ALL_ON},
    'approvals':         {'name': 'Aprobări',               'priority': 'high',     'android_channel_id': 'approval_notifications', 'defaults': _ALL_ON},
    # Communication
    'chat':              {'name': 'Mesaje',                 'priority': 'normal',   'android_channel_id': 'message_notifications'},
    'happy_announce':    {'name': 'Anunțuri',               'priority': 'normal',   'android_channel_id': 'announce_notifications'},
    'ticketing':         {'name': 'Tichete',                'priority': 'normal',   'android_channel_id': 'ticketing_notifications'},
    # HR
    'hr_attendance':     {'name': 'Pontaj',                 'priority': 'high',     'android_channel_id': 'attendance_notifications'},
    'hr_course_expiry':  {'name': 'Expirare cursuri',       'priority': 'normal',   'android_channel_id': 'hr_notifications'},
    'performance':       {'name': 'Performanță',            'priority': 'normal',   'android_channel_id': 'hr_notifications'},
    # Sales / CarPark
    'field_sales':       {'name': 'Vânzări pe teren',       'priority': 'normal',   'android_channel_id': 'field_sales_notifications'},
    'carpark':           {'name': 'Parc auto',              'priority': 'normal',   'android_channel_id': 'carpark_notifications'},
    'buyback':           {'name': 'Buy-back',               'priority': 'normal',   'android_channel_id': 'buyback_notifications'},
    'test_drive':        {'name': 'Test drive',             'priority': 'normal',   'android_channel_id': 'test_drive_notifications'},
    'marketing':         {'name': 'Marketing',              'priority': 'normal',   'android_channel_id': 'marketing_notifications'},
    # Accounting / allocations
    'accounting':        {'name': 'Contabilitate',          'priority': 'normal',   'android_channel_id': 'accounting_notifications'},
    'allocation':        {'name': 'Alocări facturi',        'priority': 'normal',   'android_channel_id': 'allocation_notifications', 'defaults': _EMAIL_ONLY},
    # Foi de parcurs / fleet
    'fp_scheduled_block': {'name': 'Blocare programată',    'priority': 'normal',   'android_channel_id': 'fp_notifications'},
    'fp_vehicle_expiry': {'name': 'Expirare documente vehicul', 'priority': 'normal', 'android_channel_id': 'fp_notifications'},
    # System-adjacent feeds / digests
    'smart_alert':       {'name': 'Alerte inteligente',     'priority': 'normal',   'android_channel_id': 'smart_notifications'},
    'digest':            {'name': 'Rezumat zilnic',         'priority': 'low',      'android_channel_id': 'digest_notifications'},
    'bnr_feed_down':     {'name': 'Curs BNR indisponibil',  'priority': 'normal',   'android_channel_id': 'system_notifications'},
}


def is_mandatory(slug):
    """True if the category is always delivered and cannot be muted."""
    return slug in MANDATORY_CATEGORIES


def default_channels(slug):
    """Default per-channel posture (fresh dict) for a category slug.

    Unknown slugs fall back to the safe standard posture (in-app + push on,
    email + SMS off) so a typo never silently enables a paid channel.
    """
    meta = CATEGORY_REGISTRY.get(slug)
    base = meta.get('defaults', _STANDARD) if meta else _STANDARD
    return dict(base)


def effective_channels(slug, pref=None):
    """Resolve the effective per-channel posture for a user + category.

    - Mandatory categories are forced ON on every channel (user cannot mute).
    - Otherwise start from the category default; an explicit (non-None) value in
      the user's preference row overrides it. A None column inherits the default,
      so only a deliberate toggle opts a user in/out.

    ``pref`` is a dict keyed by channel with bool/None values, or None.
    """
    if is_mandatory(slug):
        return {ch: True for ch in CHANNELS}
    eff = default_channels(slug)
    if pref:
        for ch in CHANNELS:
            val = pref.get(ch)
            if val is not None:
                eff[ch] = bool(val)
    return eff


def filter_recipients(user_ids, slug, channel, prefs=None):
    """Return the subset of user_ids that should receive slug on channel.

    ``prefs`` maps user_id -> preference dict (or None); users absent from it
    follow the category default. Input order is preserved.
    """
    prefs = prefs or {}
    return [uid for uid in user_ids
            if effective_channels(slug, prefs.get(uid)).get(channel)]


def build_preferences_view(rows):
    """Assemble the GET /preferences payload from a user's stored rows.

    Returns effective (defaults-applied, mandatory-forced) per-channel values for
    every registry category, plus the category list, mandatory set, and channel
    order — so the client renders without re-implementing the rules.
    """
    pref_map = {
        r['category_slug']: {
            'in_app': r.get('in_app_enabled'),
            'push': r.get('push_enabled'),
            'email': r.get('email_enabled'),
            'sms': r.get('sms_enabled'),
        }
        for r in (rows or [])
    }
    return {
        'categories': [
            {'slug': slug, 'name': meta['name'], 'mandatory': is_mandatory(slug)}
            for slug, meta in CATEGORY_REGISTRY.items()
        ],
        'preferences': {
            slug: effective_channels(slug, pref_map.get(slug))
            for slug in CATEGORY_REGISTRY
        },
        'mandatory': sorted(MANDATORY_CATEGORIES),
        'channels': list(CHANNELS),
    }


def validate_preference_update(slug):
    """Validate a POST /preferences target. Returns (message, status) on reject,
    or None if the slug may be updated by the user."""
    if slug not in CATEGORY_REGISTRY:
        return ('unknown category', 400)
    if is_mandatory(slug):
        return ('category is mandatory and cannot be changed', 422)
    return None
