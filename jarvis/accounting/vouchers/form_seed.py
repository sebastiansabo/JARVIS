"""Seed the Voucher Issuance form definition in the JARVIS Forms engine."""
import json
import logging

from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.vouchers.form_seed')

VOUCHER_FORM_SLUG = 'voucher-issuance'

VOUCHER_FORM_SCHEMA = [
    {
        'id': 'f_client_name',
        'type': 'short_text',
        'label': 'Client Name',
        'required': True,
        'placeholder': 'Full client name',
        'order': 1,
    },
    {
        'id': 'f_contract_number',
        'type': 'short_text',
        'label': 'Contract Number',
        'required': True,
        'placeholder': 'e.g. AW-2026-001',
        'order': 2,
    },
    {
        'id': 'f_car_vin',
        'type': 'short_text',
        'label': 'Car VIN (17 characters)',
        'required': True,
        'placeholder': '17-character alphanumeric VIN',
        'order': 3,
    },
    {
        'id': 'f_validity_months',
        'type': 'dropdown',
        'label': 'Validity',
        'required': True,
        'options': ['1 month', '3 months', '6 months', '12 months', '24 months'],
        'order': 4,
    },
    {
        'id': 'f_voucher_type',
        'type': 'dropdown',
        'label': 'Voucher Type',
        'required': True,
        'options': ['Value (LEI)', 'Accessory Discount Code', 'Accessory Percentage', 'Service Items'],
        'order': 5,
    },
    {
        'id': 'f_value_lei',
        'type': 'number',
        'label': 'Value (LEI)',
        'required': False,
        'placeholder': '0.00',
        'order': 6,
        'config': {'showWhen': {'fieldId': 'f_voucher_type', 'operator': 'equals', 'value': 'Value (LEI)'}},
    },
    {
        'id': 'f_discount_code',
        'type': 'short_text',
        'label': 'Discount Code',
        'required': False,
        'placeholder': 'e.g. SUMMER2026',
        'order': 7,
        'config': {'showWhen': {'fieldId': 'f_voucher_type', 'operator': 'equals', 'value': 'Accessory Discount Code'}},
    },
    {
        'id': 'f_discount_percentage',
        'type': 'number',
        'label': 'Discount Percentage (0-100)',
        'required': False,
        'placeholder': '0',
        'order': 8,
        'config': {'showWhen': {'fieldId': 'f_voucher_type', 'operator': 'equals', 'value': 'Accessory Percentage'}},
    },
    {
        'id': 'f_service_items',
        'type': 'service_catalog',
        'label': 'Service Items',
        'required': False,
        'order': 9,
        'config': {'showWhen': {'fieldId': 'f_voucher_type', 'operator': 'equals', 'value': 'Service Items'}},
    },
    {
        'id': 'f_notes',
        'type': 'long_text',
        'label': 'Notes',
        'required': False,
        'placeholder': 'Optional notes',
        'order': 10,
    },
]


def ensure_voucher_form():
    """Ensure the Voucher Issuance form exists. Idempotent."""
    base = BaseRepository()

    existing = base.query_one(
        "SELECT id FROM forms WHERE slug = %s AND deleted_at IS NULL",
        (VOUCHER_FORM_SLUG,)
    )
    if existing:
        logger.debug('Voucher issuance form already exists (id=%s)', existing['id'])
        return existing['id']

    # Get a default company and admin user for seeding
    company = base.query_one('SELECT id FROM companies ORDER BY id LIMIT 1')
    admin = base.query_one("SELECT id FROM users WHERE role_id = 1 ORDER BY id LIMIT 1")
    if not company or not admin:
        logger.warning('Cannot seed voucher form — no company or admin user found')
        return None

    form_id = base.execute('''
        INSERT INTO forms
            (name, slug, description, company_id, owner_id, created_by,
             schema, published_schema, settings, utm_config, branding,
             requires_approval, status, version, published_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'published', 1, CURRENT_TIMESTAMP)
        RETURNING id
    ''', (
        'Voucher Issuance',
        VOUCHER_FORM_SLUG,
        'Issue a voucher for a client — value, discount code, percentage, or service items.',
        company['id'],
        admin['id'],
        admin['id'],
        json.dumps(VOUCHER_FORM_SCHEMA),
        json.dumps(VOUCHER_FORM_SCHEMA),
        json.dumps({
            'thank_you_message': 'Voucher request submitted successfully! It will be reviewed by your manager.',
            'submission_limit': 10000,
        }),
        json.dumps({}),
        json.dumps({}),
        True,
    ), returning=True)

    logger.info('Seeded Voucher Issuance form (id=%s)', form_id['id'])
    return form_id['id']
