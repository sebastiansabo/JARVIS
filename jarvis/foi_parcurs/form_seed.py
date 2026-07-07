"""Seed the Test Drive form definition in the JARVIS Forms engine."""
import json
import logging

from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.foi_parcurs.form_seed')

TEST_DRIVE_FORM_SLUG = 'test-drive'

TEST_DRIVE_FORM_SCHEMA = [
    {
        'id': 'f_td_heading',
        'type': 'heading',
        'label': 'Formular Test Drive',
        'order': 1,
    },
    {
        'id': 'f_company',
        'type': 'company_select',
        'label': 'Companie',
        'required': True,
        'order': 2,
    },
    {
        'id': 'f_vehicle',
        'type': 'fp_vehicle',
        'label': 'Vehicul',
        'required': True,
        'order': 3,
        'config': {'companyField': 'f_company'},
    },
    {
        'id': 'f_client',
        'type': 'fp_client',
        'label': 'Client',
        'required': True,
        'order': 4,
    },
    {
        'id': 'f_departure',
        'type': 'datetime',
        'label': 'Data si ora plecarii',
        'required': True,
        'order': 5,
    },
    {
        'id': 'f_return',
        'type': 'datetime',
        'label': 'Data si ora intoarcerii',
        'required': False,
        'order': 6,
    },
    {
        'id': 'f_odometer_start',
        'type': 'number',
        'label': 'KM plecare',
        'required': True,
        'placeholder': 'Kilometraj la plecare',
        'order': 7,
    },
    {
        'id': 'f_odometer_end',
        'type': 'number',
        'label': 'KM sosire',
        'required': False,
        'placeholder': 'Kilometraj la sosire',
        'order': 8,
    },
    {
        'id': 'f_estimated_km',
        'type': 'number',
        'label': 'KM estimat',
        'required': True,
        'placeholder': 'Distanta estimata',
        'order': 9,
    },
    {
        'id': 'f_itinerary',
        'type': 'long_text',
        'label': 'Traseu / Itinerariu',
        'required': True,
        'placeholder': 'Descrieti traseul...',
        'order': 10,
    },
    {
        'id': 'f_fuel_start',
        'type': 'dropdown',
        'label': 'Nivel combustibil plecare',
        'required': True,
        'options': ['1', '3/4', '2/3', '1/2', '1/4'],
        'order': 11,
    },
    {
        'id': 'f_fuel_end',
        'type': 'dropdown',
        'label': 'Nivel combustibil sosire',
        'required': False,
        'options': ['1', '3/4', '2/3', '1/2', '1/4'],
        'order': 12,
    },
    {
        'id': 'f_gdpr',
        'type': 'checkbox',
        'label': 'Consimtamant GDPR',
        'required': True,
        'options': ['Accept procesarea datelor personale conform GDPR'],
        'order': 13,
    },
    {
        'id': 'f_inspection',
        'type': 'checkbox',
        'label': 'Acceptare inspectie vehicul',
        'required': True,
        'options': ['Accept starea vehiculului conform ultimei inspectii'],
        'order': 14,
    },
    {
        'id': 'f_advisor',
        'type': 'short_text',
        'label': 'Nume consilier',
        'required': True,
        'placeholder': 'Numele consilierului',
        'order': 15,
    },
    {
        'id': 'f_client_sig',
        'type': 'signature',
        'label': 'Semnatura client',
        'required': True,
        'order': 16,
    },
    {
        'id': 'f_advisor_sig',
        'type': 'signature',
        'label': 'Semnatura consilier',
        'required': True,
        'order': 17,
    },
]


def ensure_test_drive_form():
    """Ensure the Test Drive form exists. Idempotent."""
    base = BaseRepository()

    existing = base.query_one(
        "SELECT id FROM forms WHERE slug = %s AND deleted_at IS NULL",
        (TEST_DRIVE_FORM_SLUG,)
    )
    if existing:
        logger.debug('Test Drive form already exists (id=%s)', existing['id'])
        return existing['id']

    company = base.query_one('SELECT id FROM companies ORDER BY id LIMIT 1')
    admin = base.query_one("SELECT id FROM users WHERE role_id = 1 ORDER BY id LIMIT 1")
    if not company or not admin:
        logger.warning('Cannot seed test drive form — no company or admin user found')
        return None

    form_id = base.execute('''
        INSERT INTO forms
            (name, slug, description, company_id, owner_id, created_by,
             schema, published_schema, settings, utm_config, branding,
             requires_approval, published_to_hub, status, version, published_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'published', 1, CURRENT_TIMESTAMP)
        RETURNING id
    ''', (
        'Test Drive',
        TEST_DRIVE_FORM_SLUG,
        'Formular intern pentru inregistrarea test drive-urilor.',
        company['id'],
        admin['id'],
        admin['id'],
        json.dumps(TEST_DRIVE_FORM_SCHEMA),
        json.dumps(TEST_DRIVE_FORM_SCHEMA),
        json.dumps({
            'thank_you_message': 'Test Drive inregistrat cu succes!',
            'prefill': {'f_advisor': 'user.name'},
        }),
        json.dumps({}),
        json.dumps({}),
        False,
        True,
    ), returning=True)

    logger.info('Seeded Test Drive form (id=%s)', form_id['id'])
    return form_id['id']
