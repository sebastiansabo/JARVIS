"""DMS Folder Structure Sync — auto-creates Company > Year > Category folders.

Structure:
    Company Root (from companies table, auto-seeded)
    └── Year (from document doc_date, created on demand)
        └── Category (from dms_categories, created on demand)

Called from:
  - init_db (seed company roots)
  - Document create/update (ensure year + category folder exists)
  - Category CRUD hooks (when categories are added/renamed)
  - Manual sync endpoint
"""
import logging
from datetime import datetime
from core.base_repository import BaseRepository

logger = logging.getLogger('jarvis.dms.services.folder_sync')


class FolderSyncService:
    """Ensures folder structure matches companies × years × categories."""

    def __init__(self):
        self._repo = BaseRepository()

    # ── Core: resolve or create the target folder for a document ──

    # Romanian month names for folder labels
    MONTH_NAMES = {
        1: 'Ianuarie', 2: 'Februarie', 3: 'Martie', 4: 'Aprilie',
        5: 'Mai', 6: 'Iunie', 7: 'Iulie', 8: 'August',
        9: 'Septembrie', 10: 'Octombrie', 11: 'Noiembrie', 12: 'Decembrie',
    }

    def resolve_document_folder(self, company_id: int, doc_date: str | None,
                                category_name: str | None,
                                category_id: int | None = None,
                                category_icon: str = 'bi-folder',
                                category_color: str = '#6c757d',
                                created_by: int = 1,
                                include_month: bool = False) -> int | None:
        """Get or create the correct folder for a document based on its date + category.

        Path: Company Root > Year > Category [> Month]
        Returns folder_id or None if company root doesn't exist.
        """
        # 1. Find company root
        root = self._repo.query_one('''
            SELECT id, path FROM dms_folders
            WHERE company_id = %s AND parent_id IS NULL AND depth = 0
                AND deleted_at IS NULL
        ''', (company_id,))
        if not root:
            return None

        # 2. Determine year and month
        now = datetime.now()
        year_str = str(now.year)
        month_num = now.month
        if doc_date:
            try:
                year_str = str(doc_date)[:4]
                int(year_str)  # validate
                month_num = int(str(doc_date)[5:7])
            except (ValueError, IndexError):
                year_str = str(now.year)
                month_num = now.month

        # 3. Ensure year folder under company root
        year_folder = self._ensure_child(
            parent_id=root['id'],
            parent_path=root['path'],
            name=year_str,
            company_id=company_id,
            depth=1,
            sort_order=int(year_str),
            icon='bi-calendar',
            color='#0d6efd',
            created_by=created_by,
        )

        if not category_name:
            return year_folder['id']

        # 4. Ensure category folder under year
        metadata = f'{{"category_id": {category_id}}}' if category_id else '{}'
        cat_folder = self._ensure_child(
            parent_id=year_folder['id'],
            parent_path=year_folder['path'],
            name=category_name,
            company_id=company_id,
            depth=2,
            sort_order=0,
            icon=category_icon,
            color=category_color,
            created_by=created_by,
            metadata=metadata,
        )

        if not include_month:
            return cat_folder['id']

        # 5. Ensure month folder under category
        month_label = f"{month_num:02d} - {self.MONTH_NAMES.get(month_num, '')}"
        month_folder = self._ensure_child(
            parent_id=cat_folder['id'],
            parent_path=cat_folder['path'],
            name=month_label,
            company_id=company_id,
            depth=3,
            sort_order=month_num,
            icon='bi-calendar-month',
            color='#6c757d',
            created_by=created_by,
        )

        return month_folder['id']

    # ── Bulk sync (for admin panel / init) ──

    def sync_all(self, created_by: int = 1, years: list[int] | None = None):
        """Full sync: ensure every company has Year > Category subfolders.

        Args:
            created_by: user ID to attribute folder creation to
            years: list of years to create (default: current year)
        """
        if not years:
            years = [datetime.now().year]

        companies = self._repo.query_all(
            'SELECT id, company FROM companies')
        categories = self._repo.query_all(
            "SELECT id, name, icon, color, sort_order FROM dms_categories "
            "WHERE is_active = TRUE ORDER BY sort_order")

        created_roots = 0
        created_years = 0
        created_cats = 0

        for comp in companies:
            # Ensure company root folder
            root = self._repo.query_one('''
                SELECT id, path FROM dms_folders
                WHERE company_id = %s AND parent_id IS NULL AND depth = 0
                    AND deleted_at IS NULL
            ''', (comp['id'],))

            if not root:
                root = self._create_folder(
                    name=comp['company'], parent_id=None, parent_path='/',
                    company_id=comp['id'], depth=0,
                    sort_order=comp['id'], created_by=created_by)
                created_roots += 1

            for year in years:
                year_str = str(year)
                year_folder = self._ensure_child(
                    parent_id=root['id'], parent_path=root['path'],
                    name=year_str, company_id=comp['id'], depth=1,
                    sort_order=year, icon='bi-calendar', color='#0d6efd',
                    created_by=created_by)
                if year_folder.get('_created'):
                    created_years += 1

                for cat in categories:
                    metadata = f'{{"category_id": {cat["id"]}}}'
                    cat_f = self._ensure_child(
                        parent_id=year_folder['id'],
                        parent_path=year_folder['path'],
                        name=cat['name'], company_id=comp['id'], depth=2,
                        sort_order=cat.get('sort_order', 0),
                        icon=cat.get('icon', 'bi-folder'),
                        color=cat.get('color', '#6c757d'),
                        created_by=created_by, metadata=metadata)
                    if cat_f.get('_created'):
                        created_cats += 1

        result = {
            'companies': len(companies),
            'years': years,
            'categories': len(categories),
            'created': {
                'roots': created_roots,
                'year_folders': created_years,
                'category_folders': created_cats,
            }
        }
        logger.info('Folder sync complete: %s', result)
        return result

    # ── Category hooks ──

    def sync_new_category(self, category_name: str, category_id: int,
                          icon: str = 'bi-folder', color: str = '#6c757d',
                          sort_order: int = 0, created_by: int = 1):
        """When a new category is created, add folder under all existing year folders."""
        year_folders = self._repo.query_all('''
            SELECT f.id, f.path, f.company_id FROM dms_folders f
            WHERE f.depth = 1 AND f.deleted_at IS NULL
        ''')

        created = 0
        metadata = f'{{"category_id": {category_id}}}'
        for yf in year_folders:
            result = self._ensure_child(
                parent_id=yf['id'], parent_path=yf['path'],
                name=category_name, company_id=yf['company_id'], depth=2,
                sort_order=sort_order, icon=icon, color=color,
                created_by=created_by, metadata=metadata)
            if result.get('_created'):
                created += 1

        logger.info('Synced new category "%s" → %d folders', category_name, created)
        return created

    def rename_category_folders(self, old_name: str, new_name: str,
                                new_icon: str | None = None,
                                new_color: str | None = None):
        """When a category is renamed/updated, update matching folders."""
        updates = ['name = %s', 'updated_at = NOW()']
        params: list = [new_name]
        if new_icon:
            updates.append('icon = %s')
            params.append(new_icon)
        if new_color:
            updates.append('color = %s')
            params.append(new_color)

        params.extend([old_name])
        self._repo.execute(f'''
            UPDATE dms_folders SET {", ".join(updates)}
            WHERE name = %s AND depth = 2 AND deleted_at IS NULL
        ''', params)

    # ── Internal helpers ──

    def _ensure_child(self, parent_id: int, parent_path: str, name: str,
                      company_id: int, depth: int, sort_order: int = 0,
                      icon: str = 'bi-folder', color: str = '#6c757d',
                      created_by: int = 1, metadata: str = '{}') -> dict:
        """Find or create a child folder. Returns folder dict with optional _created flag."""
        existing = self._repo.query_one('''
            SELECT id, path FROM dms_folders
            WHERE parent_id = %s AND name = %s AND deleted_at IS NULL
        ''', (parent_id, name))
        if existing:
            return existing

        folder = self._create_folder(
            name=name, parent_id=parent_id, parent_path=parent_path,
            company_id=company_id, depth=depth, sort_order=sort_order,
            icon=icon, color=color, created_by=created_by, metadata=metadata)
        folder['_created'] = True
        return folder

    def _create_folder(self, name: str, parent_id: int | None, parent_path: str,
                       company_id: int, depth: int, sort_order: int = 0,
                       icon: str = 'bi-folder', color: str = '#6c757d',
                       created_by: int = 1, metadata: str = '{}') -> dict:
        """Create a folder and fix its path."""
        row = self._repo.execute('''
            INSERT INTO dms_folders
                (name, parent_id, company_id, created_by, path, depth,
                 sort_order, icon, color, metadata)
            VALUES (%s, %s, %s, %s, '/', %s, %s, %s, %s, %s)
            RETURNING id
        ''', (name, parent_id, company_id, created_by, depth,
              sort_order, icon, color, metadata), returning=True)

        real_path = f"{parent_path.rstrip('/')}/{row['id']}/"
        self._repo.execute(
            'UPDATE dms_folders SET path = %s WHERE id = %s',
            (real_path, row['id']))

        return {'id': row['id'], 'path': real_path}
