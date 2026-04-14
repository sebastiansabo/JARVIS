"""Field Sales scheduled tasks."""
import logging

logger = logging.getLogger('jarvis.tasks.field_sales')


def field_sales_follow_up_reminders():
    """Trigger 4: Notify KAMs about visits with follow-up date = tomorrow.

    Runs daily at 08:00. Checks kam_visit_notes.structured_note->>'follow_up_date'
    and sends a reminder to the assigned KAM if no follow-up visit is planned.
    """
    try:
        from datetime import date, timedelta
        from field_sales.repositories.visit_repository import VisitRepository
        from field_sales.repositories.client_fs_repository import ClientFSRepository
        from field_sales.notifications import notify_user
        from core.services.notification_service import send_email, is_smtp_configured
        from core.auth.repositories import UserRepository

        tomorrow = (date.today() + timedelta(days=1)).isoformat()
        visit_repo = VisitRepository()
        user_repo = UserRepository()

        # Find notes where follow_up_date is tomorrow
        rows = visit_repo.query_all('''
            SELECT n.visit_id, n.structured_note, v.kam_id, v.client_id,
                   c.display_name AS client_name
            FROM kam_visit_notes n
            JOIN kam_visit_plans v ON v.id = n.visit_id
            JOIN crm_clients c ON c.id = v.client_id
            WHERE n.structured_note->>'follow_up_date' = %s
        ''', (tomorrow,))

        if not rows:
            return

        smtp_ok = is_smtp_configured()
        sent = 0

        for row in rows:
            kam_id = row['kam_id']
            client_name = row.get('client_name', 'Client')

            # Check if a follow-up visit is already planned
            existing = visit_repo.query_one('''
                SELECT id FROM kam_visit_plans
                WHERE kam_id = %s AND client_id = %s
                  AND planned_date = %s AND status = 'planned'
            ''', (kam_id, row['client_id'], tomorrow))
            if existing:
                continue

            # Send reminder
            notify_user(
                kam_id,
                f'Reminder follow-up — {client_name}',
                message=f'Mâine este data de follow-up pentru {client_name}. Planifică o vizită.',
                link='/app/field-sales',
                entity_type='field_sales_visit',
                entity_id=row['visit_id'],
                type='info',
                category='field_sales',
            )

            if smtp_ok:
                user = user_repo.get_by_id(kam_id)
                email = user.get('email') if user else None
                if email:
                    send_email(
                        email,
                        f'[JARVIS] Reminder follow-up — {client_name}',
                        f'<pre>Mâine ({tomorrow}) este data de follow-up pentru {client_name}.\n\nPlanifică o vizită: https://jarvis.autoworld.ro/field-sales</pre>',
                        text_body=f'Mâine ({tomorrow}) este data de follow-up pentru {client_name}.',
                        skip_global_cc=True,
                    )
            sent += 1

        if sent:
            logger.info(f"Field Sales follow-up reminders: {sent} sent for {tomorrow}")
    except Exception as e:
        logger.error(f"Field Sales follow-up reminders failed: {e}")


def field_sales_overdue_visit_alerts():
    """Trigger 5: Alert managers about overdue visits (planned but not completed).

    Runs daily at 18:00. Checks kam_visit_plans with status='planned'
    and planned_date < today.
    """
    try:
        from datetime import date
        from field_sales.repositories.visit_repository import VisitRepository
        from core.services.notification_service import (
            send_email, get_managers_for_department, is_smtp_configured,
        )
        from core.notifications.notify import notify_users
        from core.auth.repositories import UserRepository

        today = date.today().isoformat()
        visit_repo = VisitRepository()
        user_repo = UserRepository()

        overdue = visit_repo.query_all('''
            SELECT v.id, v.kam_id, v.client_id, v.planned_date, v.visit_type,
                   c.display_name AS client_name
            FROM kam_visit_plans v
            JOIN crm_clients c ON c.id = v.client_id
            WHERE v.status = 'planned' AND v.planned_date < %s
            ORDER BY v.planned_date
        ''', (today,))

        if not overdue:
            return

        smtp_ok = is_smtp_configured()

        # Group by KAM for consolidated notifications
        by_kam = {}
        for v in overdue:
            kam_id = v['kam_id']
            if kam_id not in by_kam:
                by_kam[kam_id] = []
            by_kam[kam_id].append(v)

        notified_managers = set()

        for kam_id, visits in by_kam.items():
            user = user_repo.get_by_id(kam_id)
            if not user:
                continue
            kam_name = user.get('name', 'KAM')
            department = user.get('department')
            company = user.get('company')

            managers = get_managers_for_department(department, company) if department else []
            manager_emails = [m.get('email') for m in managers if m.get('email')]
            manager_ids = [m.get('id') for m in managers if m.get('id')]

            if not manager_ids:
                continue

            visit_lines = '\n'.join(
                f"  - {v.get('client_name', '?')} · {v.get('planned_date')} · {v.get('visit_type', 'general')}"
                for v in visits
            )

            subject = f'[JARVIS] {len(visits)} vizit{"e" if len(visits) > 1 else "ă"} restant{"e" if len(visits) > 1 else "ă"} — {kam_name}'
            body = f"""{kam_name} are {len(visits)} vizit{"e" if len(visits) > 1 else "ă"} restant{"e" if len(visits) > 1 else "ă"}:

{visit_lines}

Verificați în JARVIS Field Sales."""

            if smtp_ok:
                for email in manager_emails:
                    send_email(email, subject, f'<pre>{body}</pre>', text_body=body, skip_global_cc=True)

            # Deduplicate manager notifications
            new_ids = [mid for mid in manager_ids if mid not in notified_managers]
            if new_ids:
                notify_users(
                    new_ids,
                    f'{len(visits)} vizite restante — {kam_name}',
                    message=f'Vizite neefectuate de {kam_name}',
                    link='/app/field-sales',
                    entity_type='field_sales_visit',
                    type='warning',
                    category='field_sales',
                )
                notified_managers.update(new_ids)

        total_overdue = len(overdue)
        logger.info(f"Field Sales overdue alerts: {total_overdue} overdue visits across {len(by_kam)} KAMs")
    except Exception as e:
        logger.error(f"Field Sales overdue visit alerts failed: {e}")
