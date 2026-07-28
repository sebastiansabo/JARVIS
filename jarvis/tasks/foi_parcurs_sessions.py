"""Background job: Test Drive session lifecycle.

Every 10 minutes — (1) push the consilier once when a PLANNED session's start
hour is missed (still inside the 8h grace), (2) archive sessions past the grace
to MISSED (which frees the vehicle in conflict checks). Both passes idempotent.
"""
from core.utils.logging_config import get_logger
from foi_parcurs.repositories.foi_parcurs_repository import FoiParcursRepository
from core.notifications.notify import notify_with_push

logger = get_logger('jarvis.tasks.foi_parcurs_sessions')


def run_session_lifecycle():
    try:
        repo = FoiParcursRepository()
        for row in repo.get_sessions_pending_late_notify():
            try:
                uid = repo.get_advisor_user_id(row.get('advisor_name'))
                if uid:
                    dep = row.get('departure_datetime')
                    when = dep.strftime('%H:%M') if dep else ''
                    client = (row.get('client_name') or 'Client').strip()
                    veh = (row.get('vin') or '').strip()
                    notify_with_push(
                        [uid],
                        'Sesiune ratată la start',
                        f'{client} — {veh} la {when}. Reprogramează sau activează.',
                        link=f"/sales/test-drive/{row['id']}",
                        push_data={'link': f"/sales/test-drive/{row['id']}"},
                        entity_type='foi_parcurs_td',
                        entity_id=row['id'],
                        category='system',
                    )
                repo.mark_late_notified(row['id'])
            except Exception:
                logger.warning('late-notify failed for session %s', row.get('id'), exc_info=True)

        count = repo.archive_missed_sessions()
        if count:
            logger.info('Archived %s missed TD session(s)', count)
    except Exception as e:
        logger.error('Session lifecycle job failed: %s', e, exc_info=True)
