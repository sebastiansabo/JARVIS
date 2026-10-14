"""Repository for carpark_vehicle_consignment — the 1:1 custody (consignment)
agreement attached to a CarPark vehicle created from a failed buyback.
Written by buyback/services/carpark_handoff.py::handoff_to_carpark_custody;
read by the buyback and carpark detail GETs."""
from core.base_repository import BaseRepository

# Order matters: these map positionally to the INSERT placeholders between
# vehicle_id (first) and created_by (last).
_AGREEMENT_COLS = (
    'owner_price', 'currency', 'commission_type', 'commission_value',
    'min_sale_price', 'contract_number', 'agreement_date', 'expiry_date',
)


class ConsignmentRepository(BaseRepository):
    def create(self, vehicle_id, agreement, created_by=None):
        cols = ['vehicle_id', *(_AGREEMENT_COLS), 'created_by']
        vals = [vehicle_id, *(agreement.get(c) for c in _AGREEMENT_COLS), created_by]
        placeholders = ', '.join(['%s'] * len(cols))
        sql = (
            f'INSERT INTO carpark_vehicle_consignment ({", ".join(cols)}) '
            f'VALUES ({placeholders}) RETURNING *'
        )
        return self.execute(sql, tuple(vals), returning=True)

    def get_by_vehicle(self, vehicle_id):
        return self.query_one(
            'SELECT * FROM carpark_vehicle_consignment WHERE vehicle_id = %s',
            (vehicle_id,),
        )
