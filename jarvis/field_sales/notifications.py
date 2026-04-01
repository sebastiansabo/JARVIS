"""Field Sales notification helpers.

All notification calls are wrapped in try/except — a notification failure
must NEVER cause the primary API response to fail.

Uses:
- send_email() for email notifications (operational, always skip_global_cc)
- notify_user/notify_users for in-app + push notifications
"""

import logging
from datetime import date, datetime, timedelta

from core.services.notification_service import (
    send_email, get_managers_for_department, is_smtp_configured,
)
from core.notifications.notify import notify_user, notify_users
from core.auth.repositories import UserRepository

logger = logging.getLogger('jarvis.field_sales.notifications')

_user_repo = UserRepository()

JARVIS_URL = 'https://jarvis.autoworld.ro'


def _get_manager_emails_for_user(user_id):
    """Get email addresses of managers for a given KAM user."""
    user = _user_repo.get_by_id(user_id)
    if not user:
        return [], None
    department = user.get('department')
    company = user.get('company')
    managers = get_managers_for_department(department, company) if department else []
    emails = [m.get('email') for m in managers if m.get('email')]
    manager_ids = [m.get('id') for m in managers if m.get('id')]
    return emails, manager_ids


def _get_user_email(user_id):
    """Get email address for a user."""
    user = _user_repo.get_by_id(user_id)
    return user.get('email') if user else None


def _get_user_name(user_id):
    """Get display name for a user."""
    user = _user_repo.get_by_id(user_id)
    return user.get('name', 'KAM') if user else 'KAM'


# ═══════════════════════════════════════════════════════
# TRIGGER 1: Visit Planned → manager notification
# ═══════════════════════════════════════════════════════

def notify_visit_planned(visit, kam_name=None):
    """Notify KAM's manager when a visit is planned."""
    try:
        if not is_smtp_configured():
            return
        kam_id = visit.get('kam_id')
        kam_name = kam_name or _get_user_name(kam_id)
        client_name = visit.get('client_name', 'Client')
        planned_date = visit.get('planned_date', '')
        planned_time = visit.get('planned_time', '')
        visit_type = visit.get('visit_type', 'general')
        goals = visit.get('goals') or 'Nespecificate'

        manager_emails, manager_ids = _get_manager_emails_for_user(kam_id)
        if not manager_emails:
            return

        subject = f'[JARVIS] Vizită planificată — {client_name} · {planned_date}'
        body = f"""{kam_name} a planificat o vizită:

Client: {client_name}
Data: {planned_date} {planned_time or ''}
Tip: {visit_type}
Obiective: {goals}

Vezi detalii în JARVIS Field Sales."""

        for email in manager_emails:
            send_email(email, subject, f'<pre>{body}</pre>', text_body=body, skip_global_cc=True)

        # In-app notification for managers
        if manager_ids:
            notify_users(
                manager_ids,
                f'Vizită planificată — {client_name}',
                message=f'{kam_name}: {visit_type} · {planned_date}',
                link='/app/field-sales',
                entity_type='field_sales_visit',
                entity_id=visit.get('id'),
                type='info',
                category='field_sales',
            )
    except Exception:
        logger.exception('Failed to send visit planned notification')


# ═══════════════════════════════════════════════════════
# TRIGGER 2: High Value Opportunity → manager + KAM
# ═══════════════════════════════════════════════════════

def notify_high_value_opportunity(visit, structured_note, kam_name=None):
    """Notify when opportunity_value_eur >= 10000."""
    try:
        if not structured_note or not isinstance(structured_note, dict):
            return
        opportunity_value = structured_note.get('opportunity_value_eur')
        if not opportunity_value or opportunity_value < 10000:
            return
        if not is_smtp_configured():
            return

        kam_id = visit.get('kam_id')
        kam_name = kam_name or _get_user_name(kam_id)
        client_name = visit.get('client_name', 'Client')
        visit_summary = structured_note.get('visit_summary', '')

        # Vehicles discussed
        vehicles = structured_note.get('vehicles_discussed', [])
        vehicles_text = '\n'.join(
            f"  - {v.get('action', '?')}: {v.get('current_vehicle', '?')} → {v.get('interested_in', '?')}"
            for v in vehicles
        ) if vehicles else 'N/A'

        # Next steps
        steps = structured_note.get('next_steps', [])
        steps_text = '\n'.join(
            f"  - {s.get('action', '?')} · {s.get('owner', '?')} · {s.get('deadline', 'fără termen')}"
            for s in steps
        ) if steps else 'N/A'

        follow_up = structured_note.get('follow_up_date') or 'Nesetat'

        manager_emails, manager_ids = _get_manager_emails_for_user(kam_id)
        kam_email = _get_user_email(kam_id)

        subject = f'[JARVIS] Oportunitate {opportunity_value}€ — {client_name}'
        body = f"""{kam_name} a finalizat o vizită cu oportunitate comercială semnificativă:

Client: {client_name}
Valoare estimată: {opportunity_value}€
Vehicule discutate:
{vehicles_text}

Sumar vizită:
{visit_summary}

Pași următori:
{steps_text}

Data follow-up: {follow_up}"""

        for email in manager_emails:
            send_email(email, subject, f'<pre>{body}</pre>', text_body=body, skip_global_cc=True)
        if kam_email and kam_email not in manager_emails:
            send_email(kam_email, subject, f'<pre>{body}</pre>', text_body=body, skip_global_cc=True)

        # In-app notifications
        notify_ids = list(set((manager_ids or []) + [kam_id]))
        notify_users(
            notify_ids,
            f'Oportunitate {opportunity_value}€ — {client_name}',
            message=visit_summary[:200],
            link='/app/field-sales',
            entity_type='field_sales_visit',
            entity_id=visit.get('id'),
            type='info',
            category='field_sales',
        )
    except Exception:
        logger.exception('Failed to send high value opportunity notification')


# ═══════════════════════════════════════════════════════
# TRIGGER 3: Risk Flags Detected → manager
# ═══════════════════════════════════════════════════════

def notify_risk_flags(visit, structured_note, kam_name=None):
    """Notify manager when risk flags are detected in a visit note."""
    try:
        if not structured_note or not isinstance(structured_note, dict):
            return
        risk_flags = structured_note.get('risk_flags', [])
        if not risk_flags:
            return
        if not is_smtp_configured():
            return

        kam_id = visit.get('kam_id')
        kam_name = kam_name or _get_user_name(kam_id)
        client_name = visit.get('client_name', 'Client')
        visit_summary = structured_note.get('visit_summary', '')
        follow_up = structured_note.get('follow_up_date') or 'N/A'

        flags_text = '\n'.join(f'  {i+1}. {f}' for i, f in enumerate(risk_flags))

        manager_emails, manager_ids = _get_manager_emails_for_user(kam_id)
        if not manager_emails:
            return

        subject = f'[JARVIS] Semnale de risc — {client_name}'
        body = f"""Vizita KAM {kam_name} la {client_name} a identificat semnale de risc:

{flags_text}

Sumar vizită:
{visit_summary}

Acțiune recomandată: Revizuire cu KAM înainte de {follow_up}."""

        for email in manager_emails:
            send_email(email, subject, f'<pre>{body}</pre>', text_body=body, skip_global_cc=True)

        if manager_ids:
            notify_users(
                manager_ids,
                f'Semnale de risc — {client_name}',
                message=f'{len(risk_flags)} semnale detectate de {kam_name}',
                link='/app/field-sales',
                entity_type='field_sales_visit',
                entity_id=visit.get('id'),
                type='warning',
                category='field_sales',
            )
    except Exception:
        logger.exception('Failed to send risk flags notification')


# ═══════════════════════════════════════════════════════
# TRIGGER 6: High Renewal Score → assigned KAM
# ═══════════════════════════════════════════════════════

def notify_high_renewal_score(client_id, client_name, score, previous_score, assigned_kam_id=None):
    """Notify when renewal score crosses 75 threshold."""
    try:
        if score < 75 or (previous_score and previous_score >= 75):
            return  # Only on threshold crossing

        notify_id = assigned_kam_id
        if not notify_id:
            return

        kam_email = _get_user_email(notify_id)

        subject = f'[JARVIS] Client prioritar reînnoire — {client_name} (Scor: {score})'
        body = f"""Clientul {client_name} a atins scor de reînnoire {score}/100.

Planifică o vizită: {JARVIS_URL}/field-sales"""

        if kam_email and is_smtp_configured():
            send_email(kam_email, subject, f'<pre>{body}</pre>', text_body=body, skip_global_cc=True)

        notify_user(
            notify_id,
            f'Client prioritar reînnoire — {client_name}',
            message=f'Scor: {score}/100. Planifică o vizită.',
            link='/app/field-sales',
            entity_type='field_sales_client',
            entity_id=client_id,
            type='info',
            category='field_sales',
        )
    except Exception:
        logger.exception('Failed to send high renewal score notification')


# ═══════════════════════════════════════════════════════
# TRIGGER 7: New Business Client → assigned KAM
# ═══════════════════════════════════════════════════════

def notify_business_client_detected(client_id, client_name, profile, triggered_by_user_id=None):
    """Notify when a client is identified as business for the first time."""
    try:
        cui = profile.get('cui', '')
        legal_form = profile.get('legal_form', '')
        country_code = profile.get('country_code', '')

        notify_id = profile.get('assigned_kam_id') or triggered_by_user_id
        if not notify_id:
            return

        subject = f'[JARVIS] Client business identificat — {client_name}'
        body = f"""Clientul {client_name} a fost identificat ca persoană juridică.

CUI: {cui}
Formă juridică: {legal_form}
Țara: {country_code}

Profilul a fost actualizat în JARVIS CRM."""

        kam_email = _get_user_email(notify_id)
        if kam_email and is_smtp_configured():
            send_email(kam_email, subject, f'<pre>{body}</pre>', text_body=body, skip_global_cc=True)

        notify_user(
            notify_id,
            f'Client business identificat — {client_name}',
            message=f'CUI: {cui} · {legal_form} · {country_code}',
            link='/app/field-sales',
            entity_type='field_sales_client',
            entity_id=client_id,
            type='info',
            category='field_sales',
        )
    except Exception:
        logger.exception('Failed to send business client detection notification')
