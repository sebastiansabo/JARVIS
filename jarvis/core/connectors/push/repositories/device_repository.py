"""Mobile device repository — registration and management."""
from core.base_repository import BaseRepository


class DeviceRepository(BaseRepository):

    def count_user_devices(self, user_id):
        """Return number of registered devices for a user."""
        row = self.query_one(
            'SELECT COUNT(*) AS count FROM mobile_devices WHERE user_id = %s',
            (user_id,)
        )
        return row['count'] if row else 0

    def get_all(self):
        """Return all registered devices with user info."""
        return self.query_all('''
            SELECT md.id, md.user_id, u.name AS user_name, md.platform,
                   md.device_id, md.created_at, md.updated_at,
                   LEFT(md.push_token, 20) || '...' AS token_preview
            FROM mobile_devices md
            JOIN users u ON u.id = md.user_id
            ORDER BY md.updated_at DESC
        ''')

    def delete(self, device_id):
        """Delete a device by ID."""
        self.execute('DELETE FROM mobile_devices WHERE id = %s', (device_id,))

    def register(self, user_id, push_token, platform, device_id):
        """Upsert a device registration."""
        self.execute('''
            INSERT INTO mobile_devices (user_id, push_token, platform, device_id, updated_at)
            VALUES (%s, %s, %s, %s, NOW())
            ON CONFLICT (push_token) DO UPDATE
            SET user_id = EXCLUDED.user_id, platform = EXCLUDED.platform,
                device_id = EXCLUDED.device_id, updated_at = NOW()
        ''', (user_id, push_token, platform, device_id))

    def unregister(self, push_token, user_id):
        """Remove a device registration by push token and user."""
        self.execute(
            'DELETE FROM mobile_devices WHERE push_token = %s AND user_id = %s',
            (push_token, user_id)
        )

    def get_all_user_ids(self):
        """Return list of all user IDs with registered devices."""
        rows = self.query_all('SELECT DISTINCT user_id FROM mobile_devices')
        return [r['user_id'] if isinstance(r, dict) else r[0] for r in rows]
