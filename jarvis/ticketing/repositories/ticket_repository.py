"""Ticket and TicketComment repositories."""
from core.base_repository import BaseRepository


class TicketRepository(BaseRepository):

    def get_all(self, status=None, priority=None, category=None,
                assigned_to=None, created_by=None, search=None,
                limit=50, offset=0):
        """List tickets with optional filters. Returns dict with items + total."""
        conditions = []
        params = []

        if status:
            conditions.append('t.status = %s')
            params.append(status)
        if priority:
            conditions.append('t.priority = %s')
            params.append(priority)
        if category:
            conditions.append('t.category = %s')
            params.append(category)
        if assigned_to:
            conditions.append('t.assigned_to = %s')
            params.append(assigned_to)
        if created_by:
            conditions.append('t.created_by = %s')
            params.append(created_by)
        if search:
            conditions.append('(t.title ILIKE %s OR t.description ILIKE %s)')
            like = f'%{search}%'
            params.extend([like, like])

        where = ('WHERE ' + ' AND '.join(conditions)) if conditions else ''

        # Total count
        total_row = self.query_one(
            f'SELECT COUNT(*) AS cnt FROM tickets t {where}', params
        )
        total = total_row['cnt'] if total_row else 0

        # Items with creator/assignee info
        items = self.query_all(f'''
            SELECT t.*,
                   uc.name AS created_by_name,
                   ua.name AS assigned_to_name,
                   (SELECT COUNT(*) FROM ticket_comments tc WHERE tc.ticket_id = t.id) AS comment_count
            FROM tickets t
            LEFT JOIN users uc ON uc.id = t.created_by
            LEFT JOIN users ua ON ua.id = t.assigned_to
            {where}
            ORDER BY
                CASE t.priority
                    WHEN 'critical' THEN 1
                    WHEN 'high' THEN 2
                    WHEN 'medium' THEN 3
                    WHEN 'low' THEN 4
                END,
                t.created_at DESC
            LIMIT %s OFFSET %s
        ''', params + [limit, offset])

        return {'items': items, 'total': total}

    def get_by_id(self, ticket_id):
        """Single ticket with creator/assignee names."""
        return self.query_one('''
            SELECT t.*,
                   uc.name AS created_by_name,
                   ua.name AS assigned_to_name
            FROM tickets t
            LEFT JOIN users uc ON uc.id = t.created_by
            LEFT JOIN users ua ON ua.id = t.assigned_to
            WHERE t.id = %s
        ''', (ticket_id,))

    def create(self, title, description, priority, category, created_by):
        """Insert new ticket. Returns new ticket dict."""
        return self.execute('''
            INSERT INTO tickets (title, description, priority, category, created_by)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id, title, status, priority, category, created_by, created_at
        ''', (title, description, priority, category, created_by), returning=True)

    def update(self, ticket_id, **fields):
        """Update ticket fields. Handles status timestamp logic."""
        allowed = {'title', 'description', 'status', 'priority', 'category', 'assigned_to'}
        updates = {k: v for k, v in fields.items() if k in allowed}

        if not updates:
            return 0

        # Auto-set timestamp on status change
        if 'status' in updates:
            if updates['status'] == 'resolved':
                updates['resolved_at'] = 'NOW()'
            elif updates['status'] == 'closed':
                updates['closed_at'] = 'NOW()'
            elif updates['status'] == 'open':
                updates['resolved_at'] = None
                updates['closed_at'] = None

        set_parts = []
        params = []
        for key, val in updates.items():
            if val == 'NOW()':
                set_parts.append(f'{key} = NOW()')
            else:
                set_parts.append(f'{key} = %s')
                params.append(val)

        set_parts.append('updated_at = NOW()')
        params.append(ticket_id)

        return self.execute(
            f"UPDATE tickets SET {', '.join(set_parts)} WHERE id = %s",
            params
        )

    def delete(self, ticket_id):
        """Delete ticket (cascades to comments)."""
        return self.execute('DELETE FROM tickets WHERE id = %s', (ticket_id,))

    def get_stats(self, created_by=None):
        """Dashboard stats: counts by status."""
        condition = ''
        params = []
        if created_by:
            condition = 'WHERE created_by = %s'
            params.append(created_by)

        rows = self.query_all(f'''
            SELECT status, COUNT(*) AS cnt
            FROM tickets {condition}
            GROUP BY status
        ''', params)

        stats = {'open': 0, 'in_progress': 0, 'resolved': 0, 'closed': 0, 'total': 0}
        for row in rows:
            stats[row['status']] = row['cnt']
            stats['total'] += row['cnt']
        return stats


class TicketCommentRepository(BaseRepository):

    def get_by_ticket(self, ticket_id):
        """All comments for a ticket, with user names, ordered ASC."""
        return self.query_all('''
            SELECT tc.*, u.name AS user_name
            FROM ticket_comments tc
            LEFT JOIN users u ON u.id = tc.user_id
            WHERE tc.ticket_id = %s
            ORDER BY tc.created_at ASC
        ''', (ticket_id,))

    def create(self, ticket_id, user_id, content):
        """Add comment and update ticket.updated_at. Returns new comment dict."""
        def _work(cursor):
            cursor.execute('''
                INSERT INTO ticket_comments (ticket_id, user_id, content)
                VALUES (%s, %s, %s)
                RETURNING id, ticket_id, user_id, content, created_at
            ''', (ticket_id, user_id, content))
            comment = cursor.fetchone()
            cursor.execute(
                'UPDATE tickets SET updated_at = NOW() WHERE id = %s',
                (ticket_id,)
            )
            return comment
        from database import dict_from_row
        row = self.execute_many(_work)
        return dict_from_row(row) if row else None

    def delete(self, comment_id):
        """Delete a single comment."""
        return self.execute('DELETE FROM ticket_comments WHERE id = %s', (comment_id,))

    def get_by_id(self, comment_id):
        """Get a single comment."""
        return self.query_one(
            'SELECT * FROM ticket_comments WHERE id = %s', (comment_id,)
        )
