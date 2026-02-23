"""Repository for chart_of_accounts (Plan de Conturi)."""

from core.base_repository import BaseRepository


class ChartOfAccountsRepository(BaseRepository):

    def list_all(self, company_id=None, account_class=None, account_type=None, search=None):
        """List accounts with optional filters. Returns flat list ordered by code."""
        where = ['1=1']
        params = []
        # Show global (NULL) + company-specific
        if company_id:
            where.append('(c.company_id IS NULL OR c.company_id = %s)')
            params.append(company_id)
        else:
            where.append('c.company_id IS NULL')
        if account_class:
            where.append('c.account_class = %s')
            params.append(account_class)
        if account_type:
            where.append('c.account_type = %s')
            params.append(account_type)
        if search:
            where.append('(c.code LIKE %s OR LOWER(c.name) LIKE LOWER(%s))')
            params.extend([f'{search}%', f'%{search}%'])
        return self.query_all(f'''
            SELECT c.*, co.company as company_name
            FROM chart_of_accounts c
            LEFT JOIN companies co ON co.id = c.company_id
            WHERE {' AND '.join(where)}
            ORDER BY c.code
        ''', params)

    def get_by_id(self, account_id):
        return self.query_one(
            'SELECT * FROM chart_of_accounts WHERE id = %s', (account_id,))

    def get_by_code(self, code, company_id=None):
        if company_id:
            return self.query_one(
                'SELECT * FROM chart_of_accounts WHERE code = %s AND (company_id IS NULL OR company_id = %s)',
                (code, company_id))
        return self.query_one(
            'SELECT * FROM chart_of_accounts WHERE code = %s AND company_id IS NULL', (code,))

    def create(self, code, name, account_class, account_type='synthetic',
               parent_code=None, company_id=None):
        row = self.execute('''
            INSERT INTO chart_of_accounts (code, name, account_class, account_type, parent_code, company_id)
            VALUES (%s, %s, %s, %s, %s, %s) RETURNING id
        ''', (code, name, account_class, account_type, parent_code, company_id),
            returning=True)
        return row['id']

    def update(self, account_id, **kwargs):
        sets = []
        params = []
        for key in ('code', 'name', 'account_class', 'account_type', 'parent_code', 'is_active'):
            if key in kwargs:
                sets.append(f'{key} = %s')
                params.append(kwargs[key])
        if not sets:
            return
        sets.append('updated_at = CURRENT_TIMESTAMP')
        params.append(account_id)
        return self.execute(
            f"UPDATE chart_of_accounts SET {', '.join(sets)} WHERE id = %s", params)

    def delete(self, account_id):
        return self.execute('DELETE FROM chart_of_accounts WHERE id = %s', (account_id,))

    def get_children(self, parent_code, company_id=None):
        """Get direct children of a parent code."""
        if company_id:
            return self.query_all(
                'SELECT * FROM chart_of_accounts WHERE parent_code = %s AND (company_id IS NULL OR company_id = %s) ORDER BY code',
                (parent_code, company_id))
        return self.query_all(
            'SELECT * FROM chart_of_accounts WHERE parent_code = %s AND company_id IS NULL ORDER BY code',
            (parent_code,))

    def search_for_autocomplete(self, prefix, company_id=None, limit=20):
        """Search accounts by code prefix — for formula autocomplete."""
        where = ['c.code LIKE %s', 'c.is_active = TRUE']
        params = [f'{prefix}%']
        if company_id:
            where.append('(c.company_id IS NULL OR c.company_id = %s)')
            params.append(company_id)
        else:
            where.append('c.company_id IS NULL')
        params.append(limit)
        return self.query_all(f'''
            SELECT c.code, c.name, c.account_class, c.account_type
            FROM chart_of_accounts c
            WHERE {' AND '.join(where)}
            ORDER BY c.code
            LIMIT %s
        ''', params)
