"""Foi de Parcurs — scheduled-block boundary notifications (to-do #3).

Daily: for every active block window that STARTS or ENDS today, push an in-app +
push notification to the car's company responsables. Enforcement is dynamic and
does NOT depend on this job — this is courtesy signalling only.
"""
import logging

logger = logging.getLogger('jarvis.tasks.foi_parcurs_blocks')


def check_scheduled_blocks():
    try:
        from foi_parcurs.repositories.vehicle_repository import FPVehicleRepository
        from core.organization.repositories.company_repository import CompanyRepository
        from core.notifications.notify import notify_with_push

        veh_repo = FPVehicleRepository()
        comp_repo = CompanyRepository()
        rows = veh_repo.get_blocks_starting_or_ending_today()
        if not rows:
            logger.debug('No scheduled-block boundaries today')
            return

        resp_cache = {}
        def _responsables(cid):
            if cid not in resp_cache:
                resp_cache[cid] = [r['user_id'] for r in (comp_repo.get_responsables(cid) or [])] if cid else []
            return resp_cache[cid]

        sent = 0
        for b in rows:
            user_ids = _responsables(b.get('company_id'))
            if not user_ids:
                continue
            car = f"{(b.get('mark') or '').strip()} {(b.get('model') or '').strip()}".strip() or b['vin']
            label = f"{car} ({b.get('registration_number') or b['vin']})"
            if b['boundary'] == 'start':
                title = f'Blocare programată activă: {label}'
                msg = f'{label} este blocată de azi ({b["start_date"]}) până pe {b["end_date"]}.'
            else:
                title = f'Blocare programată încheiată: {label}'
                msg = f'{label} este disponibilă din nou (blocarea s-a încheiat azi, {b["end_date"]}).'
            notify_with_push(
                user_ids, title, message=msg,
                link='/app/foi-parcurs?tab=vehicles',
                entity_type='fp_vehicle',
                type='info',
                category='fp_scheduled_block')
            sent += 1
        logger.info(f'Sent {sent} scheduled-block boundary notifications')
    except Exception as e:
        logger.error(f'Scheduled-block notification check failed: {e}', exc_info=True)
