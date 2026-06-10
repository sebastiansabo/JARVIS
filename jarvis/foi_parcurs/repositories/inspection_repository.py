"""Data access for fp_vehicle_inspections table."""
from core.base_repository import BaseRepository


class InspectionRepository(BaseRepository):

    def create(self, data: dict) -> dict:
        cols = list(data.keys())
        placeholders = ', '.join(['%s'] * len(cols))
        col_names = ', '.join(cols)
        sql = f'INSERT INTO fp_vehicle_inspections ({col_names}) VALUES ({placeholders}) RETURNING *'
        return self.execute(sql, tuple(data[c] for c in cols), returning=True)

    def get_by_vehicle(self, vehicle_id: int) -> list:
        return self.query_all(
            'SELECT * FROM fp_vehicle_inspections WHERE vehicle_id = %s ORDER BY inspection_date DESC',
            (vehicle_id,),
        ) or []

    def get_latest(self, vehicle_id: int) -> dict | None:
        return self.query_one(
            'SELECT * FROM fp_vehicle_inspections WHERE vehicle_id = %s ORDER BY inspection_date DESC LIMIT 1',
            (vehicle_id,),
        )

    def delete(self, inspection_id: int):
        self.execute('DELETE FROM fp_vehicle_inspections WHERE id = %s', (inspection_id,))
