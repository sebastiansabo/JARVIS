"""Sincron Org Node Repository — hierarchical organigram tree for Sincron employees."""

from typing import Optional
from core.base_repository import BaseRepository


class SincronOrgNodeRepository(BaseRepository):
    """CRUD for sincron_org_nodes and sincron_org_members."""

    # ── Node CRUD ──

    def get_all(self) -> list[dict]:
        return self.query_all(
            'SELECT * FROM sincron_org_nodes ORDER BY company_id, level, display_order, name'
        )

    def get_by_company(self, company_id: int) -> list[dict]:
        return self.query_all(
            'SELECT * FROM sincron_org_nodes WHERE company_id = %s ORDER BY level, display_order, name',
            (company_id,)
        )

    def get(self, node_id: int) -> Optional[dict]:
        return self.query_one('SELECT * FROM sincron_org_nodes WHERE id = %s', (node_id,))

    def create(self, company_id: int, name: str, parent_id: int = None,
               node_type: str = 'department') -> int:
        """Create a node. Level auto-computed from parent. Max 6 levels."""
        if parent_id:
            parent = self.query_one('SELECT level FROM sincron_org_nodes WHERE id = %s', (parent_id,))
            if not parent:
                raise ValueError('Parent node not found')
            level = parent['level'] + 1
            if level > 6:
                raise ValueError('Maximum nesting depth (6 levels) reached')
        else:
            level = 1

        result = self.execute('''
            INSERT INTO sincron_org_nodes (company_id, parent_id, name, node_type, level)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id
        ''', (company_id, parent_id, name, node_type, level), returning=True)
        return result['id']

    def update(self, node_id: int, name: str = None, node_type: str = None) -> bool:
        sets, params = [], []
        if name is not None:
            sets.append('name = %s')
            params.append(name)
        if node_type is not None:
            sets.append('node_type = %s')
            params.append(node_type)
        if not sets:
            return False
        params.append(node_id)
        return self.execute(
            f'UPDATE sincron_org_nodes SET {", ".join(sets)} WHERE id = %s',
            tuple(params)
        ) > 0

    def delete(self, node_id: int) -> bool:
        return self.execute('DELETE FROM sincron_org_nodes WHERE id = %s', (node_id,)) > 0

    def reorder(self, node_id: int, display_order: int) -> bool:
        return self.execute(
            'UPDATE sincron_org_nodes SET display_order = %s WHERE id = %s',
            (display_order, node_id)
        ) > 0

    def set_parent(self, node_id: int, parent_id: Optional[int]) -> bool:
        """Move a node under a new parent (or to the root when parent_id is None).

        Recomputes ``level`` for the node and all its descendants, rejects cycles
        and > 6-level nesting, and clears an 'unallocated' node_type once the node
        is placed under a parent.
        """
        node = self.query_one(
            'SELECT company_id, parent_id, level, node_type FROM sincron_org_nodes WHERE id = %s',
            (node_id,)
        )
        if not node:
            raise ValueError('Node not found')

        # Descendants (inclusive) — needed for the cycle guard and level cascade.
        descendants = self.query_all('''
            WITH RECURSIVE sub AS (
                SELECT id, level FROM sincron_org_nodes WHERE id = %s
                UNION ALL
                SELECT c.id, c.level FROM sincron_org_nodes c JOIN sub ON c.parent_id = sub.id
            )
            SELECT id, level FROM sub
        ''', (node_id,))
        desc_ids = {r['id'] for r in descendants}

        if parent_id is None:
            new_level = 1
        else:
            if parent_id == node_id or parent_id in desc_ids:
                raise ValueError('A node cannot be moved under itself or its own descendant')
            parent = self.query_one(
                'SELECT company_id, level FROM sincron_org_nodes WHERE id = %s', (parent_id,)
            )
            if not parent:
                raise ValueError('Parent node not found')
            if parent['company_id'] != node['company_id']:
                raise ValueError('Cannot move a node to a different company')
            new_level = parent['level'] + 1

        delta = new_level - node['level']
        if max(r['level'] for r in descendants) + delta > 6:
            raise ValueError('Maximum nesting depth (6 levels) reached')

        new_type = 'department' if (parent_id is not None and node['node_type'] == 'unallocated') \
            else node['node_type']

        def _work(cursor):
            cursor.execute(
                'UPDATE sincron_org_nodes SET parent_id = %s, node_type = %s WHERE id = %s',
                (parent_id, new_type, node_id)
            )
            if delta != 0:
                cursor.execute('''
                    WITH RECURSIVE sub AS (
                        SELECT id FROM sincron_org_nodes WHERE id = %s
                        UNION ALL
                        SELECT c.id FROM sincron_org_nodes c JOIN sub ON c.parent_id = sub.id
                    )
                    UPDATE sincron_org_nodes n SET level = n.level + %s
                    FROM sub WHERE n.id = sub.id
                ''', (node_id, delta))
        self.execute_many(_work)
        return True

    # ── Member management ──

    def get_all_members(self) -> list[dict]:
        return self.query_all('''
            SELECT som.id, som.node_id, som.sincron_employee_id, som.company_name,
                   som.role, se.nume, se.prenume, se.nr_contract,
                   se.mapped_jarvis_user_id, u.name AS mapped_user_name
            FROM sincron_org_members som
            JOIN sincron_employees se
              ON se.sincron_employee_id = som.sincron_employee_id
              AND se.company_name = som.company_name
            LEFT JOIN users u ON u.id = se.mapped_jarvis_user_id
            ORDER BY som.node_id, som.role DESC, se.nume, se.prenume
        ''')

    def set_members(self, node_id: int, role: str, employee_keys: list) -> None:
        """Atomic replace: delete all members of role, insert new list.
        employee_keys: list of (sincron_employee_id, company_name) tuples.
        """
        if role not in ('responsable', 'member'):
            raise ValueError('role must be "responsable" or "member"')

        def _work(cursor):
            cursor.execute(
                'DELETE FROM sincron_org_members WHERE node_id = %s AND role = %s',
                (node_id, role)
            )
            for emp_id, comp in employee_keys:
                cursor.execute('''
                    INSERT INTO sincron_org_members (node_id, sincron_employee_id, company_name, role)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (node_id, sincron_employee_id, company_name) DO UPDATE SET role = EXCLUDED.role
                ''', (node_id, emp_id, comp, role))
            # Giving an 'unallocated' node a manager clears the flag.
            if role == 'responsable' and employee_keys:
                cursor.execute(
                    "UPDATE sincron_org_nodes SET node_type = 'department' "
                    "WHERE id = %s AND node_type = 'unallocated'",
                    (node_id,)
                )
        self.execute_many(_work)

    def add_member(self, node_id: int, sincron_employee_id: str,
                   company_name: str, role: str = 'member') -> int:
        result = self.execute('''
            INSERT INTO sincron_org_members (node_id, sincron_employee_id, company_name, role)
            VALUES (%s, %s, %s, %s)
            ON CONFLICT (node_id, sincron_employee_id, company_name) DO UPDATE SET role = EXCLUDED.role
            RETURNING id
        ''', (node_id, sincron_employee_id, company_name, role), returning=True)
        return result['id']

    def remove_member(self, node_id: int, sincron_employee_id: str, company_name: str) -> bool:
        return self.execute('''
            DELETE FROM sincron_org_members
            WHERE node_id = %s AND sincron_employee_id = %s AND company_name = %s
        ''', (node_id, sincron_employee_id, company_name)) > 0

    # ── Read-only organigram tree (powers the Sincron organigram VIEW) ──

    def get_organigram_tree(self) -> list[dict]:
        """Per-company hierarchical node tree with resolved members, plus a
        'Neatribuit' bucket of active employees assigned to no node.

        This makes the read-only organigram view mirror the node tree built in
        the editor (sincron_org_nodes / sincron_org_members) instead of grouping
        by the flat, backfill-only sincron_employees.department column — which
        left every new hire permanently under 'Neatribuit'.
        """
        employees = self.query_all('''
            SELECT se.sincron_employee_id, se.company_name,
                   se.nume, se.prenume, se.nr_contract, se.norma_lucru,
                   se.mapped_jarvis_user_id, u.name AS mapped_user_name
            FROM sincron_employees se
            LEFT JOIN users u ON u.id = se.mapped_jarvis_user_id
            WHERE se.is_active = TRUE
            ORDER BY se.company_name, se.nume, se.prenume
        ''')
        nodes = self.query_all('''
            SELECT id, company_id, parent_id, name, node_type, level, display_order
            FROM sincron_org_nodes
            ORDER BY company_id, level, display_order, name
        ''')
        members = self.query_all(
            'SELECT node_id, sincron_employee_id, company_name, role FROM sincron_org_members'
        )
        # company_name → company_id (companies table is mixed-case, sincron upper)
        id_by_name = {
            r['company'].upper(): r['id']
            for r in self.query_all('SELECT id, company FROM companies')
            if r['company']
        }

        def _emp(row):
            return {
                'sincron_employee_id': row['sincron_employee_id'],
                'company_name': row['company_name'],
                'nume': row['nume'],
                'prenume': row['prenume'],
                'nr_contract': row['nr_contract'],
                'norma_lucru': float(row['norma_lucru']) if row['norma_lucru'] is not None else None,
                'mapped_jarvis_user_id': row['mapped_jarvis_user_id'],
                'mapped_user_name': row['mapped_user_name'],
            }

        emp_by_key, emps_by_company = {}, {}
        for row in employees:
            emp = _emp(row)
            key = (row['sincron_employee_id'], row['company_name'])
            emp_by_key[key] = emp
            emps_by_company.setdefault(row['company_name'], []).append(emp)

        # Resolve members → employees; a member pointing at an inactive/removed
        # employee has no active row and is silently skipped (matches active view).
        resp_by_node, mem_by_node, assigned = {}, {}, set()
        for m in members:
            key = (m['sincron_employee_id'], m['company_name'])
            emp = emp_by_key.get(key)
            if not emp:
                continue
            assigned.add(key)
            bucket = resp_by_node if m['role'] == 'responsable' else mem_by_node
            bucket.setdefault(m['node_id'], []).append(emp)

        nodes_by_company = {}
        for n in nodes:
            nodes_by_company.setdefault(n['company_id'], []).append(n)

        def _sort_emps(lst):
            return sorted(lst, key=lambda e: ((e['nume'] or '').lower(), (e['prenume'] or '').lower()))

        def _build(company_id):
            by_id = {}
            for n in nodes_by_company.get(company_id, []):
                by_id[n['id']] = {
                    'id': n['id'], 'name': n['name'], 'node_type': n['node_type'],
                    'level': n['level'], 'parent_id': n['parent_id'],
                    'display_order': n['display_order'],
                    'responsables': _sort_emps(resp_by_node.get(n['id'], [])),
                    'members': _sort_emps(mem_by_node.get(n['id'], [])),
                    'children': [],
                }
            roots = []
            for n in nodes_by_company.get(company_id, []):
                node = by_id[n['id']]
                parent = by_id.get(n['parent_id']) if n['parent_id'] else None
                (parent['children'] if parent else roots).append(node)

            def _sort_nodes(lst):
                lst.sort(key=lambda x: (x['display_order'], (x['name'] or '').lower()))
                for x in lst:
                    _sort_nodes(x['children'])
            _sort_nodes(roots)
            return roots

        result = []
        for company_name in sorted(emps_by_company):
            company_id = id_by_name.get(company_name.upper())
            comp_emps = emps_by_company[company_name]
            unassigned = [e for e in comp_emps
                          if (e['sincron_employee_id'], company_name) not in assigned]
            result.append({
                'company_name': company_name,
                'company_id': company_id,
                'nodes': _build(company_id) if company_id is not None else [],
                'unassigned': _sort_emps(unassigned),
                'count': len(comp_emps),
                'mapped_count': sum(1 for e in comp_emps if e['mapped_jarvis_user_id']),
            })
        return result

    # ── Sincron companies (derived from sincron_employees) ──

    def get_sincron_companies(self) -> list[dict]:
        """Get companies that have active Sincron employees, with their JARVIS company_id."""
        return self.query_all('''
            SELECT DISTINCT se.company_name, c.id AS company_id
            FROM sincron_employees se
            JOIN companies c ON UPPER(c.company) = UPPER(se.company_name)
            WHERE se.is_active = TRUE
            ORDER BY se.company_name
        ''')

    # ── Seed helpers ──

    def seed_from_departments(self, company_id: int) -> dict:
        """Create L1 department nodes from sincron_employees.department + auto-assign members."""
        # Get company_name for this company_id
        comp = self.query_one('SELECT company FROM companies WHERE id = %s', (company_id,))
        if not comp:
            raise ValueError(f'Company {company_id} not found')
        company_name = comp['company']

        # Get unique departments (case-insensitive match — companies table is mixed case, sincron is uppercase)
        depts = self.query_all('''
            SELECT DISTINCT department FROM sincron_employees
            WHERE UPPER(company_name) = UPPER(%s) AND department IS NOT NULL AND is_active = TRUE
            ORDER BY department
        ''', (company_name,))

        # Get existing nodes for this company at ANY level. Dept nodes are often
        # re-parented into a hierarchy (e.g. nested under 'Aftersales' at L2), so
        # a level=1-only check would not see them and would re-create every
        # department as a fresh L1 root — doubling the tree on every re-seed.
        existing = self.query_all('''
            SELECT name FROM sincron_org_nodes
            WHERE company_id = %s
        ''', (company_id,))
        existing_names = {r['name'] for r in existing}

        # A genuinely new department is created at L1 but flagged 'unallocated'
        # so the editor surfaces it as "Nealocat" — needing a manager or a place
        # in the hierarchy. The flag clears once either is done (set_members with
        # a responsable, or set_parent). Existing nodes are never re-typed.
        created = 0
        for d in depts:
            if d['department'] not in existing_names:
                self.create(company_id, d['department'], parent_id=None, node_type='unallocated')
                created += 1

        # Auto-assign employees to their department nodes
        assigned = self._seed_members(company_id, company_name)

        return {'created': created, 'skipped': len(depts) - created, 'assigned': assigned}

    def _seed_members(self, company_id: int, company_name: str) -> int:
        """Assign employees to their department nodes based on sincron_employees.department.

        Matches the department node by name at ANY level, so members land on the
        real (possibly re-parented) node instead of a freshly-seeded L1 duplicate.
        """
        nodes = self.query_all('''
            SELECT id, name FROM sincron_org_nodes
            WHERE company_id = %s
            ORDER BY level, id
        ''', (company_id,))
        node_map = {n['name']: n['id'] for n in nodes}

        emps = self.query_all('''
            SELECT sincron_employee_id, company_name, department
            FROM sincron_employees
            WHERE UPPER(company_name) = UPPER(%s) AND department IS NOT NULL AND is_active = TRUE
        ''', (company_name,))

        assigned = 0
        for e in emps:
            nid = node_map.get(e['department'])
            if nid:
                self.execute('''
                    INSERT INTO sincron_org_members (node_id, sincron_employee_id, company_name, role)
                    VALUES (%s, %s, %s, 'member')
                    ON CONFLICT (node_id, sincron_employee_id, company_name) DO NOTHING
                ''', (nid, e['sincron_employee_id'], e['company_name']))
                assigned += 1
        return assigned
