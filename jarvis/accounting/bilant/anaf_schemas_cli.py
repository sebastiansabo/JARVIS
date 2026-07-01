"""CLI for ANAF schema management.

Usage:
    python -m accounting.bilant.anaf_schemas_cli diff <old.xsd> <new.xsd>
    python -m accounting.bilant.anaf_schemas_cli list
"""

import importlib
import os
import sys

# Import anaf_schemas directly as a module to avoid triggering
# the Flask/DB chain from accounting.bilant.__init__.py
_module_dir = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location(
    'anaf_schemas', os.path.join(_module_dir, 'anaf_schemas.py'))
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
load_schema = _mod.load_schema
SCHEMAS = _mod.SCHEMAS


def cmd_diff(old_path: str, new_path: str):
    """Print differences between two XSD schema files."""
    old = load_schema(old_path)
    new = load_schema(new_path)

    print(f'=== Schema Diff: {old_path} → {new_path} ===\n')

    if old.namespace != new.namespace:
        print(f'Namespace: {old.namespace} → {new.namespace}')

    if old.root_element != new.root_element:
        print(f'Root element: {old.root_element} → {new.root_element}')

    old_req = set(old.required_attrs)
    new_req = set(new.required_attrs)
    added_req = new_req - old_req
    removed_req = old_req - new_req
    if added_req:
        print(f'\nNew required attributes: {sorted(added_req)}')
    if removed_req:
        print(f'\nRemoved required attributes: {sorted(removed_req)}')

    old_opt = set(old.optional_attrs)
    new_opt = set(new.optional_attrs)
    added_opt = new_opt - old_opt
    removed_opt = old_opt - new_opt
    if added_opt:
        print(f'\nNew optional attributes: {sorted(added_opt)}')
    if removed_opt:
        print(f'\nRemoved optional attributes: {sorted(removed_opt)}')

    for sec in ('F10', 'F20', 'F30', 'F40'):
        old_tokens = old.valid_tokens.get(sec, set())
        new_tokens = new.valid_tokens.get(sec, set())
        added = new_tokens - old_tokens
        removed = old_tokens - new_tokens
        if added:
            print(f'\n{sec}: {len(added)} new tokens: {sorted(added)[:10]}{"..." if len(added) > 10 else ""}')
        if removed:
            print(f'\n{sec}: {len(removed)} removed tokens: {sorted(removed)[:10]}{"..." if len(removed) > 10 else ""}')
        if not added and not removed:
            print(f'\n{sec}: no token changes ({len(old_tokens)} tokens)')

    old_enums = set(old.enum_constraints)
    new_enums = set(new.enum_constraints)
    for name in sorted(old_enums | new_enums):
        old_vals = old.enum_constraints.get(name, set())
        new_vals = new.enum_constraints.get(name, set())
        if old_vals != new_vals:
            added = new_vals - old_vals
            removed = old_vals - new_vals
            if added or removed:
                print(f'\nEnum {name}: +{len(added)} -{len(removed)}')

    print('\n=== End Diff ===')


def cmd_list():
    """List all loaded schemas."""
    print('Loaded ANAF schemas:\n')
    for tip, info in sorted(SCHEMAS.items()):
        print(f'  {tip}: {info.root_element} ({info.namespace})')
        print(f'    XSD: {info.xsd_path}')
        print(f'    Required attrs: {len(info.required_attrs)}')
        print(f'    F10: {len(info.valid_tokens.get("F10", set()))} tokens')
        print(f'    F20: {len(info.valid_tokens.get("F20", set()))} tokens')
        print(f'    F30: {len(info.valid_tokens.get("F30", set()))} tokens')
        print(f'    F40: {len(info.valid_tokens.get("F40", set()))} tokens')
        print()


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == 'diff' and len(sys.argv) == 4:
        cmd_diff(sys.argv[2], sys.argv[3])
    elif cmd == 'list':
        cmd_list()
    else:
        print(__doc__)
        sys.exit(1)


if __name__ == '__main__':
    main()
