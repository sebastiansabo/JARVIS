"""Pure (no DB) test that the buyback module is registered in the sidebar
menu registry (core/settings/menus/registry.py::MODULES), so
sync_menu_items() seeds a module_menu_items row for it on next startup and
the frontend sidebar's `moduleKey: 'buyback'` check isn't silently hidden
(see Sidebar.tsx's `dbModuleMap.has(item.moduleKey)` gate).

No DB, no Flask app — MODULES is a plain Python list at import time.
"""
from core.settings.menus import registry


def test_buyback_in_module_registry():
    keys = {m['module_key'] if isinstance(m, dict) else m.module_key for m in registry.MODULES}
    assert 'buyback' in keys


def test_buyback_entry_has_required_fields():
    entry = next(
        m for m in registry.MODULES
        if (m['module_key'] if isinstance(m, dict) else m.module_key) == 'buyback'
    )
    get = (lambda k: entry[k]) if isinstance(entry, dict) else (lambda k: getattr(entry, k))
    assert get('name')
    assert get('icon')
    assert get('status') == 'active'
    assert isinstance(get('sort_order'), int)


def test_registry_still_loads_and_other_modules_untouched():
    """Sanity: touching MODULES for buyback didn't break the registry module
    or disturb the other (pre-existing) sibling entries."""
    keys = [m['module_key'] if isinstance(m, dict) else m.module_key for m in registry.MODULES]
    # No duplicate module_keys introduced.
    assert len(keys) == len(set(keys))
    for expected in ('ai_agent', 'accounting', 'hr', 'approvals', 'marketing',
                      'sales', 'dms', 'ticketing', 'aftersales', 'settings'):
        assert expected in keys
