"""Location Repository — Data access for logistics_locations and
logistics_positions (the physical yard map: location -> bays).
"""
from typing import Any, Dict, List, Optional

from core.base_repository import BaseRepository

LOCATION_FIELDS = {'name', 'code', 'company_id', 'is_active'}
POSITION_FIELDS = {'location_id', 'code', 'company_id', 'is_active'}


class LocationRepository(BaseRepository):
    """Data access for logistics_locations."""

    def list_locations(self, company_id: int = None, active_only: bool = True) -> List[Dict[str, Any]]:
        where = []
        params: list = []
        if active_only:
            where.append('is_active = TRUE')
        if company_id is not None:
            where.append('company_id = %s')
            params.append(company_id)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ''
        return self.query_all(
            f'SELECT * FROM logistics_locations {where_sql} ORDER BY name',
            tuple(params),
        )

    def get_location_by_id(self, location_id: int) -> Optional[Dict[str, Any]]:
        return self.query_one('SELECT * FROM logistics_locations WHERE id = %s', (location_id,))

    def create_location(self, data: Dict[str, Any]) -> Dict[str, Any]:
        safe_data = {k: v for k, v in data.items() if k in LOCATION_FIELDS}
        if not safe_data.get('name') or not safe_data.get('code'):
            raise ValueError('name and code are required')
        columns = list(safe_data.keys())
        return self.execute(
            f"INSERT INTO logistics_locations ({', '.join(columns)}) "
            f"VALUES ({', '.join(['%s'] * len(columns))}) RETURNING *",
            tuple(safe_data[c] for c in columns), returning=True
        )

    def update_location(self, location_id: int, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        safe_data = {k: v for k, v in patch.items() if k in LOCATION_FIELDS}
        if not safe_data:
            return self.get_location_by_id(location_id)
        sets = [f'{k} = %s' for k in safe_data]
        params = list(safe_data.values()) + [location_id]
        return self.execute(
            f"UPDATE logistics_locations SET {', '.join(sets)} WHERE id = %s RETURNING *",
            tuple(params), returning=True
        )


class PositionRepository(BaseRepository):
    """Data access for logistics_positions (bays within a location)."""

    def list_positions(self, location_id: int = None, active_only: bool = True) -> List[Dict[str, Any]]:
        where = []
        params: list = []
        if active_only:
            where.append('is_active = TRUE')
        if location_id is not None:
            where.append('location_id = %s')
            params.append(location_id)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ''
        return self.query_all(
            f'SELECT * FROM logistics_positions {where_sql} ORDER BY code',
            tuple(params),
        )

    def get_position_by_id(self, position_id: int) -> Optional[Dict[str, Any]]:
        return self.query_one('SELECT * FROM logistics_positions WHERE id = %s', (position_id,))

    def create_position(self, data: Dict[str, Any]) -> Dict[str, Any]:
        safe_data = {k: v for k, v in data.items() if k in POSITION_FIELDS}
        if not safe_data.get('location_id') or not safe_data.get('code'):
            raise ValueError('location_id and code are required')
        columns = list(safe_data.keys())
        return self.execute(
            f"INSERT INTO logistics_positions ({', '.join(columns)}) "
            f"VALUES ({', '.join(['%s'] * len(columns))}) RETURNING *",
            tuple(safe_data[c] for c in columns), returning=True
        )

    def update_position(self, position_id: int, patch: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        safe_data = {k: v for k, v in patch.items() if k in POSITION_FIELDS}
        if not safe_data:
            return self.get_position_by_id(position_id)
        sets = [f'{k} = %s' for k in safe_data]
        params = list(safe_data.values()) + [position_id]
        return self.execute(
            f"UPDATE logistics_positions SET {', '.join(sets)} WHERE id = %s RETURNING *",
            tuple(params), returning=True
        )
