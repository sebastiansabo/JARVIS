"""mkt_project entity handlers."""
import logging
from database import get_db, get_cursor, release_db

logger = logging.getLogger('jarvis.core.approvals.handlers.entity_marketing')


def handle_submitted(entity_id):
    try:
        from marketing.repositories import ProjectRepository
        ProjectRepository().update_status(entity_id, 'pending_approval')
    except Exception as e:
        logger.error(f'Failed to set mkt_project pending_approval on submit: {e}')


def handle_approved(entity_id, request_id, requester_id):
    try:
        from marketing.repositories import ProjectRepository, ActivityRepository
        ProjectRepository().update_status(entity_id, 'approved')
        conn = get_db()
        try:
            cursor = get_cursor(conn)
            cursor.execute('''
                UPDATE mkt_budget_lines
                SET approved_amount = planned_amount, status = 'approved', updated_at = NOW()
                WHERE project_id = %s AND status = 'draft'
            ''', (entity_id,))
            conn.commit()
        finally:
            release_db(conn)
        ActivityRepository().log(entity_id, 'approval_decided', actor_type='system',
                                 details={'decision': 'approved'})
        logger.info(f'Marketing project #{entity_id} approved via approval hook')
    except Exception as e:
        logger.error(f'Failed to update mkt_project status on approval: {e}')


def handle_rejected(entity_id):
    try:
        from marketing.repositories import ProjectRepository, ActivityRepository
        ProjectRepository().update_status(entity_id, 'draft')
        ActivityRepository().log(entity_id, 'approval_decided', actor_type='system',
                                 details={'decision': 'rejected'})
    except Exception as e:
        logger.error(f'Failed to revert mkt_project status on rejection: {e}')


def handle_returned(entity_id, comment=''):
    try:
        from marketing.repositories import ProjectRepository, ActivityRepository
        ProjectRepository().update_status(entity_id, 'draft')
        ActivityRepository().log(entity_id, 'approval_decided', actor_type='system',
                                 details={'decision': 'returned', 'comment': comment})
    except Exception as e:
        logger.error(f'Failed to revert mkt_project status on return: {e}')
