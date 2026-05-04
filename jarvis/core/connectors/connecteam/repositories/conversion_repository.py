"""Leave-permit CO conversion data access layer."""

from core.base_repository import BaseRepository


class ConversionRepository(BaseRepository):
    """CRUD for leave_permit_conversions + linked submissions."""

    def create(self, *, employee_user_id, year, month, total_accumulated_hours,
               co_days_requested, approver_user_id, requested_by,
               approval_request_id, submission_ids):
        """Create conversion request and link submission IDs."""
        row = self.execute(
            """
            INSERT INTO leave_permit_conversions
                (employee_user_id, year, month, total_accumulated_hours,
                 co_days_requested, approver_user_id, requested_by,
                 approval_request_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (employee_user_id, year, month, total_accumulated_hours,
             co_days_requested, approver_user_id, requested_by,
             approval_request_id),
            returning=True,
        )
        conversion_id = row['id']

        for sid in submission_ids:
            self.execute(
                """
                INSERT INTO leave_permit_conversion_submissions
                    (conversion_id, submission_id)
                VALUES (%s, %s)
                """,
                (conversion_id, sid),
            )
        return conversion_id

    def set_approval_request_id(self, conversion_id, approval_request_id):
        self.execute(
            "UPDATE leave_permit_conversions SET approval_request_id = %s WHERE id = %s",
            (approval_request_id, conversion_id),
        )

    def get_by_id(self, conversion_id):
        return self.query_one(
            """
            SELECT lpc.*,
                   eu.name AS employee_name,
                   au.name AS approver_name,
                   ru.name AS requested_by_name
            FROM leave_permit_conversions lpc
            LEFT JOIN users eu ON eu.id = lpc.employee_user_id
            LEFT JOIN users au ON au.id = lpc.approver_user_id
            LEFT JOIN users ru ON ru.id = lpc.requested_by
            WHERE lpc.id = %s
            """,
            (conversion_id,),
        )

    def get_for_employee_month(self, employee_user_id, year, month):
        """Check if a pending conversion already exists."""
        return self.query_one(
            """
            SELECT id, status FROM leave_permit_conversions
            WHERE employee_user_id = %s AND year = %s AND month = %s
              AND status = 'pending'
            """,
            (employee_user_id, year, month),
        )

    def update_status(self, conversion_id, status, resolved_by=None):
        self.execute(
            """
            UPDATE leave_permit_conversions
            SET status = %s, resolved_at = NOW()
            WHERE id = %s
            """,
            (status, conversion_id),
        )

    def get_submission_ids(self, conversion_id):
        rows = self.query_all(
            "SELECT submission_id FROM leave_permit_conversion_submissions WHERE conversion_id = %s",
            (conversion_id,),
        )
        return [r['submission_id'] for r in rows]

    def get_for_month(self, year, month):
        return self.query_all(
            """
            SELECT lpc.id, lpc.employee_user_id, lpc.co_days_requested,
                   lpc.total_accumulated_hours, lpc.status, lpc.created_at,
                   eu.name AS employee_name,
                   au.name AS approver_name
            FROM leave_permit_conversions lpc
            LEFT JOIN users eu ON eu.id = lpc.employee_user_id
            LEFT JOIN users au ON au.id = lpc.approver_user_id
            WHERE lpc.year = %s AND lpc.month = %s
            ORDER BY lpc.created_at DESC
            """,
            (year, month),
        )
