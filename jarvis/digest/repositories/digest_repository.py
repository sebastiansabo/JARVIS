"""Repository for digest module — channels, posts, reactions, polls."""

from core.base_repository import BaseRepository


class DigestRepository(BaseRepository):

    # ── Channels ─────────────────────────────────────────────

    def get_channels(self, user_id):
        """Get all channels the user is a member of (or all public channels)."""
        return self.query_all('''
            SELECT c.*, u.name AS created_by_name,
                   (SELECT COUNT(*) FROM digest_channel_members WHERE channel_id = c.id) AS member_count,
                   (SELECT COUNT(*) FROM digest_posts WHERE channel_id = c.id AND deleted_at IS NULL) AS post_count,
                   COALESCE(
                       (SELECT COUNT(*) FROM digest_posts p
                        WHERE p.channel_id = c.id AND p.deleted_at IS NULL
                          AND p.id > COALESCE(
                              (SELECT last_read_post_id FROM digest_read_status
                               WHERE channel_id = c.id AND user_id = %s), 0
                          )
                       ), 0
                   ) AS unread_count
            FROM digest_channels c
            LEFT JOIN users u ON u.id = c.created_by
            WHERE c.deleted_at IS NULL
              AND (c.is_private = FALSE
                   OR EXISTS (SELECT 1 FROM digest_channel_members m
                              WHERE m.channel_id = c.id AND m.user_id = %s))
            ORDER BY c.created_at DESC
        ''', (user_id, user_id))

    def get_channel(self, channel_id):
        return self.query_one('''
            SELECT c.*, u.name AS created_by_name
            FROM digest_channels c
            LEFT JOIN users u ON u.id = c.created_by
            WHERE c.id = %s AND c.deleted_at IS NULL
        ''', (channel_id,))

    def create_channel(self, name, description, channel_type, is_private, created_by):
        return self.execute('''
            INSERT INTO digest_channels (name, description, type, is_private, created_by)
            VALUES (%s, %s, %s, %s, %s) RETURNING *
        ''', (name, description, channel_type, is_private, created_by), returning=True)

    def update_channel(self, channel_id, name, description):
        return self.execute('''
            UPDATE digest_channels SET name = %s, description = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND deleted_at IS NULL RETURNING *
        ''', (name, description, channel_id), returning=True)

    def delete_channel(self, channel_id):
        return self.execute('''
            UPDATE digest_channels SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s
        ''', (channel_id,))

    # ── Channel Members ──────────────────────────────────────

    def get_channel_members(self, channel_id):
        return self.query_all('''
            SELECT m.*, u.name AS user_name, u.email AS user_email
            FROM digest_channel_members m
            JOIN users u ON u.id = m.user_id
            WHERE m.channel_id = %s
            ORDER BY m.role DESC, u.name
        ''', (channel_id,))

    def add_member(self, channel_id, user_id, role='member'):
        return self.execute('''
            INSERT INTO digest_channel_members (channel_id, user_id, role)
            VALUES (%s, %s, %s)
            ON CONFLICT (channel_id, user_id) DO NOTHING
            RETURNING *
        ''', (channel_id, user_id, role), returning=True)

    def remove_member(self, channel_id, user_id):
        return self.execute('''
            DELETE FROM digest_channel_members WHERE channel_id = %s AND user_id = %s
        ''', (channel_id, user_id))

    def is_member(self, channel_id, user_id):
        row = self.query_one('''
            SELECT 1 FROM digest_channel_members WHERE channel_id = %s AND user_id = %s
        ''', (channel_id, user_id))
        return row is not None

    def add_all_active_users(self, channel_id):
        """Add all active users as members of a channel."""
        return self.execute('''
            INSERT INTO digest_channel_members (channel_id, user_id, role)
            SELECT %s, id, 'member' FROM users WHERE is_active = TRUE
            ON CONFLICT (channel_id, user_id) DO NOTHING
        ''', (channel_id,))

    # ── Posts ────────────────────────────────────────────────

    def get_posts(self, channel_id, limit=50, offset=0, parent_id=None):
        """Get top-level posts or replies to a specific parent."""
        if parent_id:
            return self.query_all('''
                SELECT p.*, u.name AS user_name,
                       (SELECT COUNT(*) FROM digest_posts r WHERE r.parent_id = p.id AND r.deleted_at IS NULL) AS reply_count,
                       rp.id AS reply_to_post_id, rp.content AS reply_to_content,
                       ru.name AS reply_to_user_name
                FROM digest_posts p
                JOIN users u ON u.id = p.user_id
                LEFT JOIN digest_posts rp ON rp.id = p.reply_to_id
                LEFT JOIN users ru ON ru.id = rp.user_id
                WHERE p.channel_id = %s AND p.parent_id = %s AND p.deleted_at IS NULL
                ORDER BY p.created_at ASC
                LIMIT %s OFFSET %s
            ''', (channel_id, parent_id, limit, offset))
        return self.query_all('''
            SELECT p.*, u.name AS user_name,
                   (SELECT COUNT(*) FROM digest_posts r WHERE r.parent_id = p.id AND r.deleted_at IS NULL) AS reply_count,
                   rp.id AS reply_to_post_id, rp.content AS reply_to_content,
                   ru.name AS reply_to_user_name
            FROM digest_posts p
            JOIN users u ON u.id = p.user_id
            LEFT JOIN digest_posts rp ON rp.id = p.reply_to_id
            LEFT JOIN users ru ON ru.id = rp.user_id
            WHERE p.channel_id = %s AND p.parent_id IS NULL AND p.deleted_at IS NULL
            ORDER BY p.is_pinned DESC, p.created_at DESC
            LIMIT %s OFFSET %s
        ''', (channel_id, limit, offset))

    def get_post(self, post_id):
        return self.query_one('''
            SELECT p.*, u.name AS user_name
            FROM digest_posts p
            JOIN users u ON u.id = p.user_id
            WHERE p.id = %s AND p.deleted_at IS NULL
        ''', (post_id,))

    def create_post(self, channel_id, user_id, content, post_type='post', parent_id=None, reply_to_id=None):
        return self.execute('''
            INSERT INTO digest_posts (channel_id, user_id, content, type, parent_id, reply_to_id)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING *
        ''', (channel_id, user_id, content, post_type, parent_id, reply_to_id), returning=True)

    def update_post(self, post_id, content):
        return self.execute('''
            UPDATE digest_posts SET content = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND deleted_at IS NULL RETURNING *
        ''', (content, post_id), returning=True)

    def delete_post(self, post_id):
        return self.execute('''
            UPDATE digest_posts SET deleted_at = CURRENT_TIMESTAMP WHERE id = %s
        ''', (post_id,))

    def toggle_pin(self, post_id):
        return self.execute('''
            UPDATE digest_posts SET is_pinned = NOT is_pinned, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND deleted_at IS NULL RETURNING *
        ''', (post_id,), returning=True)

    # ── Reactions ────────────────────────────────────────────

    def get_reactions(self, post_id):
        return self.query_all('''
            SELECT r.emoji, COUNT(*) AS count,
                   ARRAY_AGG(u.name ORDER BY r.created_at) AS user_names,
                   ARRAY_AGG(r.user_id ORDER BY r.created_at) AS user_ids
            FROM digest_reactions r
            JOIN users u ON u.id = r.user_id
            WHERE r.post_id = %s
            GROUP BY r.emoji
            ORDER BY MIN(r.created_at)
        ''', (post_id,))

    def toggle_reaction(self, post_id, user_id, emoji):
        """Toggle a reaction. Returns 'added' or 'removed'."""
        existing = self.query_one('''
            SELECT id FROM digest_reactions WHERE post_id = %s AND user_id = %s AND emoji = %s
        ''', (post_id, user_id, emoji))
        if existing:
            self.execute('DELETE FROM digest_reactions WHERE id = %s', (existing['id'],))
            return 'removed'
        self.execute('''
            INSERT INTO digest_reactions (post_id, user_id, emoji) VALUES (%s, %s, %s)
        ''', (post_id, user_id, emoji))
        return 'added'

    # ── Polls ────────────────────────────────────────────────

    def create_poll(self, post_id, question, options, is_multiple_choice=False, closes_at=None):
        def _work(cursor):
            cursor.execute('''
                INSERT INTO digest_polls (post_id, question, is_multiple_choice, closes_at)
                VALUES (%s, %s, %s, %s) RETURNING *
            ''', (post_id, question, is_multiple_choice, closes_at))
            poll = cursor.fetchone()
            poll_id = poll[0]
            for i, opt in enumerate(options):
                cursor.execute('''
                    INSERT INTO digest_poll_options (poll_id, option_text, sort_order)
                    VALUES (%s, %s, %s)
                ''', (poll_id, opt, i))
            return poll_id
        return self.execute_many(_work)

    def get_poll(self, post_id):
        poll = self.query_one('''
            SELECT * FROM digest_polls WHERE post_id = %s
        ''', (post_id,))
        if not poll:
            return None
        poll['options'] = self.query_all('''
            SELECT o.*, COUNT(v.id) AS vote_count
            FROM digest_poll_options o
            LEFT JOIN digest_poll_votes v ON v.option_id = o.id
            WHERE o.poll_id = %s
            GROUP BY o.id
            ORDER BY o.sort_order
        ''', (poll['id'],))
        poll['total_votes'] = sum(o['vote_count'] for o in poll['options'])
        return poll

    def get_user_votes(self, poll_id, user_id):
        return self.query_all('''
            SELECT option_id FROM digest_poll_votes WHERE poll_id = %s AND user_id = %s
        ''', (poll_id, user_id))

    def vote(self, poll_id, option_id, user_id):
        """Cast a vote. For single-choice, removes previous vote first."""
        poll = self.query_one('SELECT is_multiple_choice FROM digest_polls WHERE id = %s', (poll_id,))
        if not poll:
            return None
        if not poll['is_multiple_choice']:
            self.execute('DELETE FROM digest_poll_votes WHERE poll_id = %s AND user_id = %s', (poll_id, user_id))
        return self.execute('''
            INSERT INTO digest_poll_votes (poll_id, option_id, user_id) VALUES (%s, %s, %s)
            ON CONFLICT (poll_id, option_id, user_id) DO NOTHING
            RETURNING *
        ''', (poll_id, option_id, user_id), returning=True)

    def unvote(self, poll_id, option_id, user_id):
        return self.execute('''
            DELETE FROM digest_poll_votes WHERE poll_id = %s AND option_id = %s AND user_id = %s
        ''', (poll_id, option_id, user_id))

    # ── Read Status ──────────────────────────────────────────

    def mark_read(self, channel_id, user_id, post_id):
        return self.execute('''
            INSERT INTO digest_read_status (channel_id, user_id, last_read_post_id, last_read_at)
            VALUES (%s, %s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (channel_id, user_id)
            DO UPDATE SET last_read_post_id = GREATEST(digest_read_status.last_read_post_id, EXCLUDED.last_read_post_id),
                          last_read_at = CURRENT_TIMESTAMP
        ''', (channel_id, user_id, post_id))

    def get_unread_counts(self, user_id):
        return self.query_all('''
            SELECT c.id AS channel_id, c.name,
                   COUNT(p.id) AS unread_count
            FROM digest_channels c
            LEFT JOIN digest_read_status rs ON rs.channel_id = c.id AND rs.user_id = %s
            LEFT JOIN digest_posts p ON p.channel_id = c.id
                AND p.deleted_at IS NULL
                AND p.id > COALESCE(rs.last_read_post_id, 0)
            WHERE c.deleted_at IS NULL
              AND (c.is_private = FALSE
                   OR EXISTS (SELECT 1 FROM digest_channel_members m WHERE m.channel_id = c.id AND m.user_id = %s))
            GROUP BY c.id, c.name
            HAVING COUNT(p.id) > 0
        ''', (user_id, user_id))
