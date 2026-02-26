"""
Module Registry — single source of truth for all sidebar modules.

Add a new feature here and it auto-appears in Settings > Menus on next startup.
The sidebar reads from the DB (populated from this registry) to control visibility & ordering.

Frontend Sidebar.tsx maps `module_key` → React components (icons, badges, children routes).
"""

import logging

logger = logging.getLogger('jarvis.core.settings.menus.registry')

# Parent modules — top-level sidebar items
MODULES = [
    {
        'module_key': 'ai_agent',
        'name': 'AI Agent',
        'description': 'AI Assistant & Chat',
        'icon': 'bi-robot',
        'url': '/ai-agent',
        'color': '#6366f1',
        'status': 'active',
        'sort_order': 1,
    },
    {
        'module_key': 'accounting',
        'name': 'Accounting',
        'description': 'Invoices, Budgets, Statements',
        'icon': 'bi-calculator',
        'url': '/accounting',
        'color': '#0d6efd',
        'status': 'active',
        'sort_order': 2,
        'children': [
            {'module_key': 'accounting_dashboard', 'name': 'Invoices', 'description': 'View invoices', 'icon': 'bi-grid-1x2', 'url': '/accounting', 'sort_order': 1},
            {'module_key': 'accounting_statements', 'name': 'Statements', 'description': 'Parse bank statements', 'icon': 'bi-bank', 'url': '/statements/', 'sort_order': 2},
            {'module_key': 'accounting_efactura', 'name': 'e-Factura', 'description': 'ANAF e-Factura sync', 'icon': 'bi-file-earmark-text', 'url': '/efactura', 'sort_order': 3},
            {'module_key': 'accounting_bilant', 'name': 'Bilant', 'description': 'Balance sheet generator', 'icon': 'bi-clipboard-data', 'url': '/accounting/bilant', 'sort_order': 4},
            {'module_key': 'accounting_add', 'name': 'Add Invoice', 'description': 'Create new invoice', 'icon': 'bi-plus-circle', 'url': '/add-invoice', 'sort_order': 5},
            {'module_key': 'accounting_templates', 'name': 'Templates', 'description': 'Manage parsing templates', 'icon': 'bi-file-earmark-code', 'url': '/templates', 'sort_order': 6},
        ],
    },
    {
        'module_key': 'hr',
        'name': 'HR',
        'description': 'Events, Bonuses, Employees',
        'icon': 'bi-people',
        'url': '/hr/events/',
        'color': '#9c27b0',
        'status': 'active',
        'sort_order': 3,
        'children': [
            {'module_key': 'hr_events', 'name': 'Event Bonuses', 'description': 'Manage bonuses', 'icon': 'bi-gift', 'url': '/hr/events/', 'sort_order': 1},
            {'module_key': 'hr_manage_events', 'name': 'Manage Events', 'description': 'Create/edit events', 'icon': 'bi-calendar-event', 'url': '/hr/events/events', 'sort_order': 2},
            {'module_key': 'hr_employees', 'name': 'Employees', 'description': 'Employee list', 'icon': 'bi-person-lines-fill', 'url': '/hr/events/employees', 'sort_order': 3},
        ],
    },
    {
        'module_key': 'approvals',
        'name': 'Approvals',
        'description': 'Approval Workflows',
        'icon': 'bi-check2-square',
        'url': '/approvals',
        'color': '#f59e0b',
        'status': 'active',
        'sort_order': 4,
    },
    {
        'module_key': 'marketing',
        'name': 'Marketing',
        'description': 'Campaigns & Content',
        'icon': 'bi-megaphone',
        'url': '/marketing',
        'color': '#ec4899',
        'status': 'active',
        'sort_order': 5,
    },
    {
        'module_key': 'sales',
        'name': 'Sales',
        'description': 'CRM, Deals & Client Management',
        'icon': 'bi-cart3',
        'url': '/sales',
        'color': '#dc3545',
        'status': 'active',
        'sort_order': 6,
        'children': [
            {'module_key': 'crm_database', 'name': 'CRM Database', 'description': 'Client & deal management', 'icon': 'bi-person-lines-fill', 'url': '/sales/crm', 'sort_order': 1},
        ],
    },
    {
        'module_key': 'dms',
        'name': 'Documents',
        'description': 'Document Management System',
        'icon': 'bi-folder',
        'url': '/dms',
        'color': '#0ea5e9',
        'status': 'active',
        'sort_order': 7,
    },
    {
        'module_key': 'aftersales',
        'name': 'After Sales',
        'description': 'Service, Warranty, Support',
        'icon': 'bi-tools',
        'url': '#',
        'color': '#198754',
        'status': 'coming_soon',
        'sort_order': 8,
    },
    {
        'module_key': 'settings',
        'name': 'Settings',
        'description': 'System Configuration',
        'icon': 'bi-gear',
        'url': '/settings',
        'color': '#6c757d',
        'status': 'active',
        'sort_order': 9,
    },
]


def sync_menu_items(cursor):
    """Sync registry → DB. Inserts missing items, updates sort_order.

    Called once on startup from init_db(). Idempotent — safe to re-run.
    Does NOT delete items that exist in DB but not in registry (user may
    have added custom items via Settings UI).
    """
    # Fetch existing module_keys from DB
    cursor.execute('SELECT id, module_key, parent_id FROM module_menu_items')
    existing = {row['module_key']: row for row in cursor.fetchall()}

    added = 0
    for mod in MODULES:
        mkey = mod['module_key']

        if mkey not in existing:
            # Insert parent
            cursor.execute('''
                INSERT INTO module_menu_items
                    (module_key, name, description, icon, url, color, status, sort_order)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
            ''', (mkey, mod['name'], mod['description'], mod['icon'],
                  mod['url'], mod['color'], mod['status'], mod['sort_order']))
            parent_id = cursor.fetchone()['id']
            existing[mkey] = {'id': parent_id, 'module_key': mkey, 'parent_id': None}
            added += 1
            logger.info(f'Menu sync: inserted parent "{mkey}"')
        else:
            parent_id = existing[mkey]['id']
            # Update sort_order to match registry
            cursor.execute(
                'UPDATE module_menu_items SET sort_order = %s WHERE id = %s AND sort_order != %s',
                (mod['sort_order'], parent_id, mod['sort_order']))

        # Children
        for child in mod.get('children', []):
            ckey = child['module_key']
            if ckey not in existing:
                cursor.execute('''
                    INSERT INTO module_menu_items
                        (parent_id, module_key, name, description, icon, url, color, status, sort_order)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (parent_id, ckey, child['name'], child['description'],
                      child.get('icon', 'bi-grid'), child.get('url', '#'),
                      mod.get('color', '#6c757d'), child.get('status', 'active'),
                      child['sort_order']))
                existing[ckey] = {'id': None, 'module_key': ckey, 'parent_id': parent_id}
                added += 1
                logger.info(f'Menu sync: inserted child "{ckey}" under "{mkey}"')
            else:
                # Repair parent_id if wrong (e.g. old migration left it NULL)
                existing_child = existing[ckey]
                if existing_child['parent_id'] != parent_id:
                    cursor.execute(
                        'UPDATE module_menu_items SET parent_id = %s WHERE module_key = %s',
                        (parent_id, ckey))
                    logger.info(f'Menu sync: fixed parent_id for "{ckey}" → "{mkey}"')

    if added:
        logger.info(f'Menu sync complete — {added} new item(s) added')
    else:
        logger.debug('Menu sync — all items present')
