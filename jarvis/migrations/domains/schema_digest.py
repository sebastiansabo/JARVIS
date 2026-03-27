"""Digest module schema: channels, posts, reactions, polls, read-tracking."""


def create_schema_digest(conn, cursor):
    """Create digest/communication module tables."""

    # ============== Channels ==============

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS digest_channels (
            id SERIAL PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT,
            type TEXT NOT NULL DEFAULT 'general',
            is_private BOOLEAN DEFAULT FALSE,
            created_by INTEGER REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP,
            CONSTRAINT digest_channels_type_check CHECK (type IN (
                'general', 'announcement', 'department'
            ))
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_digest_channels_type ON digest_channels(type) WHERE deleted_at IS NULL')

    # ============== Channel Members ==============

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS digest_channel_members (
            id SERIAL PRIMARY KEY,
            channel_id INTEGER NOT NULL REFERENCES digest_channels(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            role TEXT NOT NULL DEFAULT 'member',
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT digest_channel_members_role_check CHECK (role IN ('admin', 'member')),
            CONSTRAINT digest_channel_members_unique UNIQUE (channel_id, user_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_digest_channel_members_user ON digest_channel_members(user_id)')

    # ============== Posts ==============

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS digest_posts (
            id SERIAL PRIMARY KEY,
            channel_id INTEGER NOT NULL REFERENCES digest_channels(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            content TEXT NOT NULL,
            type TEXT NOT NULL DEFAULT 'post',
            is_pinned BOOLEAN DEFAULT FALSE,
            parent_id INTEGER REFERENCES digest_posts(id) ON DELETE CASCADE,
            reply_to_id INTEGER REFERENCES digest_posts(id) ON DELETE SET NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            deleted_at TIMESTAMP,
            CONSTRAINT digest_posts_type_check CHECK (type IN ('post', 'announcement', 'poll'))
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_digest_posts_channel ON digest_posts(channel_id, created_at DESC) WHERE deleted_at IS NULL')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_digest_posts_parent ON digest_posts(parent_id) WHERE deleted_at IS NULL')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_digest_posts_user ON digest_posts(user_id) WHERE deleted_at IS NULL')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_digest_posts_pinned ON digest_posts(channel_id) WHERE is_pinned = TRUE AND deleted_at IS NULL')

    # ============== Reactions ==============

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS digest_reactions (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES digest_posts(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            emoji TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT digest_reactions_unique UNIQUE (post_id, user_id, emoji)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_digest_reactions_post ON digest_reactions(post_id)')

    # ============== Polls ==============

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS digest_polls (
            id SERIAL PRIMARY KEY,
            post_id INTEGER NOT NULL REFERENCES digest_posts(id) ON DELETE CASCADE,
            question TEXT NOT NULL,
            is_multiple_choice BOOLEAN DEFAULT FALSE,
            closes_at TIMESTAMP,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS digest_poll_options (
            id SERIAL PRIMARY KEY,
            poll_id INTEGER NOT NULL REFERENCES digest_polls(id) ON DELETE CASCADE,
            option_text TEXT NOT NULL,
            sort_order INTEGER DEFAULT 0
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS digest_poll_votes (
            id SERIAL PRIMARY KEY,
            poll_id INTEGER NOT NULL REFERENCES digest_polls(id) ON DELETE CASCADE,
            option_id INTEGER NOT NULL REFERENCES digest_poll_options(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT digest_poll_votes_unique UNIQUE (poll_id, option_id, user_id)
        )
    ''')
    cursor.execute('CREATE INDEX IF NOT EXISTS idx_digest_poll_votes_poll ON digest_poll_votes(poll_id)')

    # ============== Read Status ==============

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS digest_read_status (
            id SERIAL PRIMARY KEY,
            channel_id INTEGER NOT NULL REFERENCES digest_channels(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id),
            last_read_post_id INTEGER REFERENCES digest_posts(id) ON DELETE SET NULL,
            last_read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            CONSTRAINT digest_read_status_unique UNIQUE (channel_id, user_id)
        )
    ''')

    conn.commit()
