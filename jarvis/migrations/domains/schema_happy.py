"""Happy module schema — internal employee engagement.

Phase 1 (surface engine, web-only): campaigns, declarative audience, materialized
targets, per-user UI state, click-acknowledgement, raw analytics events (30-day
retention), daily rollups, and the frequency governor.

Praise (§7.4), Pulse (§7.5), notification prefs (§7.6) and quiz comprehension
(§7.2 quiz tables) are created by later phases. DDL is idempotent and follows the
repo convention: CREATE TABLE IF NOT EXISTS + IF NOT EXISTS indexes.

Ordering: registered after create_schema_digest / create_schema_core so FKs to
public.users(id) and public.digest_posts(id) resolve.
"""


def create_schema_happy(conn, cursor):
    """Create the `happy` schema, Phase 1 tables, and seed permissions_v2."""

    cursor.execute('CREATE SCHEMA IF NOT EXISTS happy')
    conn.commit()

    # ============== Campaigns & delivery (§7.1) ==============

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS happy.campaigns (
            id              SERIAL PRIMARY KEY,
            slug            TEXT UNIQUE NOT NULL,
            kind            TEXT NOT NULL,              -- hr_announcement|event|action|policy|survey|recognition
            tier            TEXT NOT NULL DEFAULT 'normal',   -- critical|important|normal
            placements      TEXT[] NOT NULL,            -- {interstitial,dash_banner,hub_card,feed,push,email}
            locale          TEXT NOT NULL DEFAULT 'ro',
            kicker          TEXT,
            title           TEXT NOT NULL,
            summary         TEXT,
            body_md         TEXT,
            media_key       TEXT,                       -- DO Spaces key under private/happy/…, served via /api/media/<key>
            media_alt       TEXT,
            cta_label       TEXT,
            cta_href        TEXT,
            cta_deeplink    TEXT,
            event_at        TIMESTAMPTZ,                -- for event campaigns
            ack_mode        TEXT NOT NULL DEFAULT 'none',     -- none|click|quiz
            ack_deadline_at TIMESTAMPTZ,
            dismissible     BOOLEAN NOT NULL DEFAULT TRUE,
            escalation      JSONB NOT NULL DEFAULT '{}'::jsonb,
            status          TEXT NOT NULL DEFAULT 'draft',    -- draft|scheduled|live|paused|archived
            starts_at       TIMESTAMPTZ,
            ends_at         TIMESTAMPTZ,                -- REQUIRED at publish; <= starts_at + 90 days (enforced in service)
            digest_post_id  INTEGER REFERENCES public.digest_posts(id) ON DELETE SET NULL,
            source_type     TEXT,                       -- hr_event|manual|pulse|system
            source_id       INTEGER,
            created_by      INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
            approved_by     INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
            published_at    TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    ''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_happy_campaigns_live
        ON happy.campaigns (status, starts_at, ends_at) WHERE status = 'live' ''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_happy_campaigns_placements
        ON happy.campaigns USING GIN (placements)''')

    # Declarative audience rules (authoring representation)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS happy.campaign_audience (
            id          SERIAL PRIMARY KEY,
            campaign_id INTEGER NOT NULL REFERENCES happy.campaigns(id) ON DELETE CASCADE,
            mode        TEXT NOT NULL,        -- include|exclude
            dimension   TEXT NOT NULL,        -- company|brand|department|subdepartment|org_unit|role|contract_status|user
            value       TEXT NOT NULL
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_happy_audience_campaign ON happy.campaign_audience(campaign_id)')

    # Materialized resolved audience. Refreshed at publish + nightly (new-joiner inheritance).
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS happy.campaign_targets (
            campaign_id INTEGER NOT NULL REFERENCES happy.campaigns(id) ON DELETE CASCADE,
            user_id     INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (campaign_id, user_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_happy_targets_user ON happy.campaign_targets(user_id)')

    # Per-user per-campaign UI state (dismissals, snoozes). Not analytics.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS happy.campaign_state (
            campaign_id     INTEGER NOT NULL REFERENCES happy.campaigns(id) ON DELETE CASCADE,
            user_id         INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            snooze_count    SMALLINT NOT NULL DEFAULT 0,
            snoozed_until   TIMESTAMPTZ,
            dismiss_count   SMALLINT NOT NULL DEFAULT 0,
            dismissed_until TIMESTAMPTZ,
            first_seen_at   TIMESTAMPTZ,
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (campaign_id, user_id)
        )
    ''')

    # ============== Acknowledgement (§7.2 — click mode; quiz tables in Phase 2) ==============

    # Compliance record. Legal basis = contract/legal obligation, NOT monitoring.
    # Retained per the document-retention policy, not the 30-day analytics cap.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS happy.acknowledgements (
            id              SERIAL PRIMARY KEY,
            campaign_id     INTEGER NOT NULL REFERENCES happy.campaigns(id) ON DELETE CASCADE,
            user_id         INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            acknowledged_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            method          TEXT NOT NULL,        -- click|quiz
            surface         TEXT NOT NULL,        -- interstitial|hub_card|feed|email
            attempts        SMALLINT DEFAULT 1,
            UNIQUE (campaign_id, user_id)
        )
    ''')

    # ============== Analytics — retention-sensitive (§7.3) ==============

    # RAW EVENTS. 30-day hard retention (Law 190/2018 Art. 5). Purged nightly.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS happy.campaign_events (
            id           BIGSERIAL PRIMARY KEY,
            campaign_id  INTEGER NOT NULL REFERENCES happy.campaigns(id) ON DELETE CASCADE,
            user_id      INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
            surface      TEXT NOT NULL,
            event_type   TEXT NOT NULL,     -- impression|read|click|dismiss|snooze|ack|push_sent|push_open
            dwell_ms     INTEGER,
            platform     TEXT,              -- web|android
            created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    ''')
    cursor.execute('''CREATE INDEX IF NOT EXISTS idx_happy_events_campaign_day
        ON happy.campaign_events (campaign_id, created_at DESC)''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_happy_events_purge ON happy.campaign_events (created_at)')

    # ROLLUP. Survives the purge. No user_id — aggregate by cohort only.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS happy.campaign_daily_stats (
            campaign_id  INTEGER NOT NULL REFERENCES happy.campaigns(id) ON DELETE CASCADE,
            day          DATE NOT NULL,
            cohort_key   TEXT NOT NULL DEFAULT 'all',   -- 'all' | 'dept:Vanzari' | 'company:AutoWorld'
            targeted     INTEGER NOT NULL DEFAULT 0,
            reached      INTEGER NOT NULL DEFAULT 0,    -- >=1 impression
            read_8s      INTEGER NOT NULL DEFAULT 0,
            clicked      INTEGER NOT NULL DEFAULT 0,
            acknowledged INTEGER NOT NULL DEFAULT 0,
            dismissed    INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (campaign_id, day, cohort_key)
        )
    ''')

    # Frequency governor. Feeds the resolver's cap check.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS happy.frequency_ledger (
            user_id     INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            day         DATE NOT NULL,
            placement   TEXT NOT NULL,
            shown_count SMALLINT NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, day, placement)
        )
    ''')

    conn.commit()

    _create_phase2(conn, cursor)
    _seed_permissions(conn, cursor)


def _create_phase2(conn, cursor):
    """Phase 2 — compliance depth: quiz comprehension, audit log, escalation state."""

    # Comprehension quiz (§7.2). AGGREGATE stats only — quiz_question_stats never
    # stores a user_id or a per-person answer.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS happy.quiz_questions (
            id            SERIAL PRIMARY KEY,
            campaign_id   INTEGER NOT NULL REFERENCES happy.campaigns(id) ON DELETE CASCADE,
            position      SMALLINT NOT NULL,
            prompt        TEXT NOT NULL,
            options       JSONB NOT NULL,          -- ["a","b","c"]
            correct_index SMALLINT NOT NULL,
            CHECK (position BETWEEN 1 AND 5),
            UNIQUE (campaign_id, position)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_happy_quiz_campaign ON happy.quiz_questions(campaign_id)')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS happy.quiz_question_stats (
            question_id   INTEGER PRIMARY KEY REFERENCES happy.quiz_questions(id) ON DELETE CASCADE,
            attempts      INTEGER NOT NULL DEFAULT 0,
            first_correct INTEGER NOT NULL DEFAULT 0
        )
    ''')

    # Durable audit trail. Unlike campaign_events (30-day purge), audit rows survive:
    # critical bypasses, cap overrides, escalation steps off default, compliance exports.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS happy.audit_log (
            id            BIGSERIAL PRIMARY KEY,
            campaign_id   INTEGER REFERENCES happy.campaigns(id) ON DELETE SET NULL,
            actor_user_id INTEGER REFERENCES public.users(id) ON DELETE SET NULL,
            action        TEXT NOT NULL,           -- critical_bypass|cap_override|escalation_step|compliance_export|publish
            detail        JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_happy_audit_campaign ON happy.audit_log(campaign_id, created_at DESC)')

    # Per (campaign,user) escalation progress so a step never fires twice.
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS happy.escalation_state (
            campaign_id   INTEGER NOT NULL REFERENCES happy.campaigns(id) ON DELETE CASCADE,
            user_id       INTEGER NOT NULL REFERENCES public.users(id) ON DELETE CASCADE,
            last_step     SMALLINT NOT NULL DEFAULT 0,   -- 0 none · 1 +48h push · 2 +5d email · 3 +7d mgr · 4 deadline · 5 +3d export
            last_fired_at TIMESTAMPTZ,
            PRIMARY KEY (campaign_id, user_id)
        )
    ''')

    conn.commit()


# §8.3 — permissions to seed in permissions_v2. (module_key, entity_key, entity_label,
# action_key, action_label, description, is_scope_based)
_HAPPY_PERMISSIONS = [
    ('campaigns',  'Campaigns',  'view',    'View',    'View campaigns',                     True),
    ('campaigns',  'Campaigns',  'edit',    'Edit',    'Create and edit campaigns',          False),
    ('campaigns',  'Campaigns',  'publish', 'Publish', 'Publish / pause campaigns',          False),
    ('campaigns',  'Campaigns',  'escalate','Escalate','Escalate unacknowledged campaigns',  False),
    ('compliance', 'Compliance', 'export',  'Export',  'Export the acknowledgement list',    False),
    ('pulse',      'Pulse',      'manage',  'Manage',  'Create and manage pulses',           False),
    ('pulse',      'Pulse',      'results', 'Results', 'View pulse results',                 True),
    ('praise',     'Praise',     'moderate','Moderate','Moderate flagged recognition',       False),
    ('praise',     'Praise',     'grant',   'Grant',   'Manual point adjustments',           False),
    ('admin',      'Admin',      'manage',  'Manage',  'Happy settings, categories, tags',   False),
]


def _seed_permissions(conn, cursor):
    """Idempotently register Happy permissions and grant them to the Admin role.

    Uses the repo's established idiom: an unconditional INSERT ... ON CONFLICT
    DO NOTHING per permission (re-runs safely on every init) plus a matching
    role-grant for the Admin role.
    """
    for idx, (entity_key, entity_label, action_key, action_label, description, scoped) in enumerate(_HAPPY_PERMISSIONS):
        cursor.execute(
            '''INSERT INTO permissions_v2
                   (module_key, module_label, module_icon, entity_key, entity_label,
                    action_key, action_label, description, is_scope_based, sort_order)
               VALUES ('happy', 'Happy', 'bi-emoji-smile', %s, %s, %s, %s, %s, %s, %s)
               ON CONFLICT (module_key, entity_key, action_key) DO NOTHING''',
            (entity_key, entity_label, action_key, action_label, description, scoped, idx),
        )
        cursor.execute(
            '''INSERT INTO role_permissions_v2 (role_id, permission_id, scope, granted)
               SELECT r.id, p.id, 'all', TRUE
                 FROM roles r
                 CROSS JOIN permissions_v2 p
                WHERE r.name = 'Admin'
                  AND p.module_key = 'happy' AND p.entity_key = %s AND p.action_key = %s
               ON CONFLICT (role_id, permission_id) DO NOTHING''',
            (entity_key, action_key),
        )
    conn.commit()
