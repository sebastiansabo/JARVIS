"""
Company Connection Repository

Database operations for e-Factura company connections.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any

from core.database import get_db, get_cursor
from core.utils.logging_config import get_logger
from ..models import CompanyConnection

logger = get_logger('jarvis.accounting.efactura.repo.company')


class CompanyConnectionRepository:
    """Repository for CompanyConnection entities."""

    def create(self, connection: CompanyConnection) -> CompanyConnection:
        """
        Create a new company connection.

        Args:
            connection: CompanyConnection to create

        Returns:
            Created CompanyConnection with ID
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            cursor.execute("""
                INSERT INTO efactura_company_connections (
                    cif, display_name, environment, status, status_message,
                    config, cert_fingerprint, cert_expires_at,
                    created_at, updated_at
                ) VALUES (
                    %(cif)s, %(display_name)s, %(environment)s, %(status)s,
                    %(status_message)s, %(config)s, %(cert_fingerprint)s,
                    %(cert_expires_at)s, NOW(), NOW()
                )
                RETURNING id, created_at, updated_at
            """, {
                'cif': connection.cif,
                'display_name': connection.display_name,
                'environment': connection.environment,
                'status': connection.status,
                'status_message': connection.status_message,
                'config': connection.config,
                'cert_fingerprint': connection.cert_fingerprint,
                'cert_expires_at': connection.cert_expires_at,
            })

            row = cursor.fetchone()
            connection.id = row['id']
            connection.created_at = row['created_at']
            connection.updated_at = row['updated_at']

            conn.commit()

            logger.info(
                "Company connection created",
                extra={'cif': connection.cif, 'id': connection.id}
            )

            return connection

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to create company connection: {e}")
            raise

    def get_by_cif(self, cif: str) -> Optional[CompanyConnection]:
        """
        Get company connection by CIF.

        Args:
            cif: Company tax ID

        Returns:
            CompanyConnection or None
        """
        conn = get_db()
        cursor = get_cursor(conn)

        cursor.execute("""
            SELECT * FROM efactura_company_connections
            WHERE cif = %s
        """, (cif,))

        row = cursor.fetchone()
        if row is None:
            return None

        return self._row_to_model(row)

    def get_by_id(self, connection_id: int) -> Optional[CompanyConnection]:
        """Get company connection by ID."""
        conn = get_db()
        cursor = get_cursor(conn)

        cursor.execute("""
            SELECT * FROM efactura_company_connections
            WHERE id = %s
        """, (connection_id,))

        row = cursor.fetchone()
        if row is None:
            return None

        return self._row_to_model(row)

    def get_all_active(self) -> List[CompanyConnection]:
        """Get all active company connections."""
        conn = get_db()
        cursor = get_cursor(conn)

        cursor.execute("""
            SELECT * FROM efactura_company_connections
            WHERE status = 'active'
            ORDER BY display_name
        """)

        return [self._row_to_model(row) for row in cursor.fetchall()]

    def get_for_sync(self) -> List[CompanyConnection]:
        """Get companies that need synchronization."""
        conn = get_db()
        cursor = get_cursor(conn)

        # Get active connections that haven't synced in the last hour
        cursor.execute("""
            SELECT * FROM efactura_company_connections
            WHERE status = 'active'
            AND (
                last_sync_at IS NULL
                OR last_sync_at < NOW() - INTERVAL '1 hour'
            )
            ORDER BY last_sync_at NULLS FIRST
        """)

        return [self._row_to_model(row) for row in cursor.fetchall()]

    def update(self, connection: CompanyConnection) -> CompanyConnection:
        """
        Update a company connection.

        Args:
            connection: CompanyConnection with updated values

        Returns:
            Updated CompanyConnection
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            cursor.execute("""
                UPDATE efactura_company_connections SET
                    display_name = %(display_name)s,
                    environment = %(environment)s,
                    status = %(status)s,
                    status_message = %(status_message)s,
                    config = %(config)s,
                    cert_fingerprint = %(cert_fingerprint)s,
                    cert_expires_at = %(cert_expires_at)s,
                    updated_at = NOW()
                WHERE id = %(id)s
                RETURNING updated_at
            """, {
                'id': connection.id,
                'display_name': connection.display_name,
                'environment': connection.environment,
                'status': connection.status,
                'status_message': connection.status_message,
                'config': connection.config,
                'cert_fingerprint': connection.cert_fingerprint,
                'cert_expires_at': connection.cert_expires_at,
            })

            row = cursor.fetchone()
            connection.updated_at = row['updated_at']

            conn.commit()

            logger.info(
                "Company connection updated",
                extra={'cif': connection.cif, 'id': connection.id}
            )

            return connection

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update company connection: {e}")
            raise

    def update_sync_cursor(
        self,
        cif: str,
        received_cursor: Optional[str] = None,
        sent_cursor: Optional[str] = None,
    ):
        """
        Update sync cursors after successful sync.

        Args:
            cif: Company CIF
            received_cursor: New cursor for received messages
            sent_cursor: New cursor for sent messages
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            updates = ['last_sync_at = NOW()', 'updated_at = NOW()']
            params = {'cif': cif}

            if received_cursor is not None:
                updates.append('last_received_cursor = %(received_cursor)s')
                params['received_cursor'] = received_cursor

            if sent_cursor is not None:
                updates.append('last_sent_cursor = %(sent_cursor)s')
                params['sent_cursor'] = sent_cursor

            cursor.execute(f"""
                UPDATE efactura_company_connections SET
                    {', '.join(updates)}
                WHERE cif = %(cif)s
            """, params)

            conn.commit()

            logger.debug(
                "Sync cursor updated",
                extra={'cif': cif}
            )

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update sync cursor: {e}")
            raise

    def update_status(
        self,
        cif: str,
        status: str,
        message: Optional[str] = None,
    ):
        """
        Update connection status.

        Args:
            cif: Company CIF
            status: New status
            message: Status message
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            cursor.execute("""
                UPDATE efactura_company_connections SET
                    status = %s,
                    status_message = %s,
                    updated_at = NOW()
                WHERE cif = %s
            """, (status, message, cif))

            conn.commit()

            logger.info(
                "Company status updated",
                extra={'cif': cif, 'status': status}
            )

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to update status: {e}")
            raise

    def delete(self, cif: str) -> bool:
        """
        Delete a company connection.

        Args:
            cif: Company CIF

        Returns:
            True if deleted
        """
        conn = get_db()
        cursor = get_cursor(conn)

        try:
            cursor.execute("""
                DELETE FROM efactura_company_connections
                WHERE cif = %s
            """, (cif,))

            deleted = cursor.rowcount > 0
            conn.commit()

            if deleted:
                logger.info(
                    "Company connection deleted",
                    extra={'cif': cif}
                )

            return deleted

        except Exception as e:
            conn.rollback()
            logger.error(f"Failed to delete company connection: {e}")
            raise

    def _row_to_model(self, row: Dict[str, Any]) -> CompanyConnection:
        """Convert database row to CompanyConnection model."""
        return CompanyConnection(
            id=row['id'],
            cif=row['cif'],
            display_name=row['display_name'],
            environment=row['environment'],
            last_sync_at=row.get('last_sync_at'),
            last_received_cursor=row.get('last_received_cursor'),
            last_sent_cursor=row.get('last_sent_cursor'),
            status=row['status'],
            status_message=row.get('status_message'),
            config=row.get('config') or {},
            cert_fingerprint=row.get('cert_fingerprint'),
            cert_expires_at=row.get('cert_expires_at'),
            created_at=row['created_at'],
            updated_at=row['updated_at'],
        )
