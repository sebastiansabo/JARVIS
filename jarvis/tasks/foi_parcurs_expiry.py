"""Foi de Parcurs — vehicle document expiry alerts (Rovinietă / RCA / ITP).

Daily check: for every active car whose Rovinietă (vignette), RCA (insurance) or
ITP is expired or within 30 days, notify the car's company — an email to the
company's `alert_email` and an in-app + push notification to the company's L0
responsables. A 7-day cooldown per (car, document) avoids daily spam.
"""
import logging

logger = logging.getLogger('jarvis.tasks.foi_parcurs_expiry')


def check_vehicle_document_expiry():
    try:
        from foi_parcurs.repositories.vehicle_repository import FPVehicleRepository
        from core.organization.repositories.company_repository import CompanyRepository
        from core.notifications.notify import notify_with_push
        from core.services.notification_service import send_email
        from database import get_db, get_cursor, release_db

        veh_repo = FPVehicleRepository()
        comp_repo = CompanyRepository()

        expiring = veh_repo.get_documents_expiring(days_ahead=30)
        if not expiring:
            logger.debug('No vehicle documents expiring in the next 30 days')
            return
        logger.info(f'Found {len(expiring)} vehicle documents expiring within 30 days')

        comp_cache = {}

        def _company(cid):
            if cid not in comp_cache:
                row = comp_repo.get(cid) or {} if cid else {}
                resp = comp_repo.get_responsables(cid) if cid else []
                comp_cache[cid] = {
                    'alert_email': (row.get('alert_email') or '').strip(),
                    'name': row.get('company') or '',
                    'user_ids': [r['user_id'] for r in resp],
                }
            return comp_cache[cid]

        conn = get_db()
        try:
            cursor = get_cursor(conn)
            sent = 0
            for d in expiring:
                vin, doc, days, valid = d['vin'], d['doc'], int(d['days']), d['valid_until']
                veh_id = d['id']
                # 7-day cooldown per (car, document) via smart_notification_state
                # (alert_type, entity_type=doc, entity_id=vehicle id).
                cursor.execute(
                    "SELECT 1 FROM smart_notification_state WHERE alert_type='fp_vehicle_expiry' "
                    "AND entity_type=%s AND entity_id=%s "
                    "AND last_alerted_at > CURRENT_TIMESTAMP - INTERVAL '7 days'", (doc, veh_id))
                if cursor.fetchone():
                    continue

                comp = _company(d.get('company_id'))
                car = f"{(d.get('mark') or '').strip()} {(d.get('model') or '').strip()}".strip() or vin
                label = f"{car} ({d.get('registration_number') or vin})"
                if days < 0:
                    title = f'{doc} EXPIRAT: {label}'
                    msg = f'{doc} pentru {label} a expirat pe {valid} (acum {abs(days)} zile).'
                elif days == 0:
                    title = f'{doc} expiră azi: {label}'
                    msg = f'{doc} pentru {label} expiră astăzi ({valid}).'
                else:
                    title = f'{doc} expiră în {days} zile: {label}'
                    msg = f'{doc} pentru {label} expiră pe {valid} (în {days} zile).'

                if comp['user_ids']:
                    notify_with_push(
                        comp['user_ids'], title, message=msg,
                        link='/app/foi-parcurs?tab=vehicles',
                        entity_type='fp_vehicle',
                        type='warning' if days <= 7 else 'info',
                        category='fp_vehicle_expiry')
                if comp['alert_email']:
                    html = f'<p>{msg}</p><p>Companie: {comp["name"]}</p>'
                    try:
                        send_email(comp['alert_email'], title, html, text_body=msg)
                    except Exception:
                        logger.warning('Vehicle expiry email failed for %s', comp['alert_email'], exc_info=True)

                cursor.execute(
                    "INSERT INTO smart_notification_state (alert_type, entity_type, entity_id, last_alerted_at) "
                    "VALUES ('fp_vehicle_expiry', %s, %s, CURRENT_TIMESTAMP) "
                    "ON CONFLICT (alert_type, entity_type, entity_id) "
                    "DO UPDATE SET last_alerted_at = CURRENT_TIMESTAMP", (doc, veh_id))
                sent += 1

            conn.commit()
            logger.info(f'Sent {sent} vehicle document expiry notifications')
        finally:
            release_db(conn)
    except Exception as e:
        logger.error(f'Vehicle document expiry check failed: {e}', exc_info=True)
