"""BNR FX-feed health monitor.

Daily check that the BNR EUR/RON reference rate is fetchable. BNR moved the
rate feed to the ``curs.bnr.ro`` subdomain in Aug 2026 with only a couple of
days' notice (notice #25710); when the auto-fetch silently breaks, every EUR
invoice falls back to manual ``Curs BNR`` entry. This task alerts the L0
owners/admins (in-app + push + email) so the endpoint can be updated before it
disrupts invoicing. A 20-hour cooldown avoids duplicate alerts across scheduler
restarts and the daily re-run while the feed stays down.
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger('jarvis.tasks.bnr_monitor')


def check_bnr_feed():
    """Verify the BNR EUR rate is fetchable; alert L0 owners/admins if not."""
    try:
        from core.services.currency_converter import get_exchange_rate, clear_cache
        from core.notifications.notify import notify_with_push
        from core.services.notification_service import send_email
        from database import get_db, get_cursor, release_db

        # Rate for yesterday — what an invoice issued today would use. BNR carries
        # the last publishing day forward over weekends/holidays, so a non-None
        # result here means the feed reached us and parsed.
        kurs_date = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
        rate = get_exchange_rate('EUR', kurs_date)
        if rate is None:
            # One retry with a fresh cache to rule out a transient blip / an
            # empty cache left by an earlier failed fetch, before crying wolf.
            clear_cache()
            rate = get_exchange_rate('EUR', kurs_date)
        if rate:
            logger.debug('BNR feed OK: EUR@%s = %s', kurs_date, rate)
            return

        logger.error('BNR feed check FAILED: no EUR rate resolved for %s', kurs_date)

        conn = get_db()
        try:
            cursor = get_cursor(conn)
            # 20h cooldown on a single system-wide key so a restart or the next
            # daily run does not re-spam while the feed is still down.
            cursor.execute(
                "SELECT 1 FROM smart_notification_state WHERE alert_type='bnr_feed_down' "
                "AND entity_type='system' AND entity_id=0 "
                "AND last_alerted_at > CURRENT_TIMESTAMP - INTERVAL '20 hours'")
            if cursor.fetchone():
                logger.info('BNR feed still down but within alert cooldown; not re-alerting')
                return

            cursor.execute("SELECT DISTINCT user_id FROM company_responsables")
            l0_ids = [r['user_id'] for r in cursor.fetchall()]

            title = 'Curs BNR indisponibil — facturarea EUR necesită curs manual'
            msg = (
                f'Preluarea automată a cursului BNR a eșuat (fără curs EUR pentru {kurs_date}). '
                'Verifică dacă feed-ul https://curs.bnr.ro/nbrfxrates.xml mai este disponibil — '
                'până la remediere, facturile în EUR necesită introducerea manuală a cursului.'
            )
            if l0_ids:
                notify_with_push(
                    l0_ids, title, message=msg,
                    link='/app/accounting',
                    type='warning',
                    category='bnr_feed_down')
                cursor.execute(
                    "SELECT email FROM users WHERE id = ANY(%s) AND email IS NOT NULL", (l0_ids,))
                html = f'<p>{msg}</p>'
                for row in cursor.fetchall():
                    addr = (row['email'] or '').strip()
                    if not addr:
                        continue
                    try:
                        send_email(addr, title, html, text_body=msg)
                    except Exception:
                        logger.warning('BNR feed-down email failed for %s', addr, exc_info=True)

            cursor.execute(
                "INSERT INTO smart_notification_state (alert_type, entity_type, entity_id, last_alerted_at) "
                "VALUES ('bnr_feed_down', 'system', 0, CURRENT_TIMESTAMP) "
                "ON CONFLICT (alert_type, entity_type, entity_id) "
                "DO UPDATE SET last_alerted_at = CURRENT_TIMESTAMP")
            conn.commit()
            logger.info('BNR feed-down alert sent to %d L0 user(s)', len(l0_ids))
        finally:
            release_db(conn)
    except Exception as e:
        logger.error('BNR feed monitor failed: %s', e, exc_info=True)
