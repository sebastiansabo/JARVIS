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

    # ── Seed helpers ──

    def seed_from_departments(self, company_id: int) -> dict:
        """Create L1 department nodes from sincron_employees.department + auto-assign members."""
        # Get company_name for this company_id
        comp = self.query_one('SELECT company FROM companies WHERE id = %s', (company_id,))
        if not comp:
            raise ValueError(f'Company {company_id} not found')
        company_name = comp['company']

        # Get unique departments
        depts = self.query_all('''
            SELECT DISTINCT department FROM sincron_employees
            WHERE company_name = %s AND department IS NOT NULL AND is_active = TRUE
            ORDER BY department
        ''', (company_name,))

        # Get existing L1 nodes for this company
        existing = self.query_all('''
            SELECT name FROM sincron_org_nodes
            WHERE company_id = %s AND level = 1
        ''', (company_id,))
        existing_names = {r['name'] for r in existing}

        created = 0
        for d in depts:
            if d['department'] not in existing_names:
                self.create(company_id, d['department'], parent_id=None, node_type='department')
                created += 1

        # Auto-assign employees to their department nodes
        assigned = self._seed_members(company_id, company_name)

        return {'created': created, 'skipped': len(depts) - created, 'assigned': assigned}

    def _seed_members(self, company_id: int, company_name: str) -> int:
        """Assign employees to their department nodes based on sincron_employees.department."""
        nodes = self.query_all('''
            SELECT id, name FROM sincron_org_nodes
            WHERE company_id = %s AND level = 1
        ''', (company_id,))
        node_map = {n['name']: n['id'] for n in nodes}

        emps = self.query_all('''
            SELECT sincron_employee_id, company_name, department
            FROM sincron_employees
            WHERE company_name = %s AND department IS NOT NULL AND is_active = TRUE
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
