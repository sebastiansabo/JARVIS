"""Fuel gauge conversion and proportional distribution logic."""

FUEL_LEVELS = {
    '1': 1.0,
    '1/2': 0.5,
    '2/3': 0.667,
    '1/4': 0.25,
}


def parse_fuel_level(level_str: str) -> float:
    """Convert categorical fuel level string to decimal fraction."""
    if level_str not in FUEL_LEVELS:
        raise ValueError(
            f"Invalid fuel level: {level_str}. "
            f"Must be one of {list(FUEL_LEVELS.keys())}"
        )
    return FUEL_LEVELS[level_str]


def calculate_fuel_distribution(
    fuel_tank_capacity_liters: int,
    fuel_gauge_start_level: str,
    fuel_gauge_end_level: str,
    total_consumption_period_liters: float,
    distances_per_client: list,
) -> dict:
    """Distribute fuel consumption proportionally across clients based on distance.

    Returns dict with:
      - start_liters, end_liters, available_consumption
      - per_client: list of {fuel_start_liters, fuel_end_liters, fuel_consumed_liters}
    """
    start_fraction = parse_fuel_level(fuel_gauge_start_level)
    end_fraction = parse_fuel_level(fuel_gauge_end_level)

    start_liters = start_fraction * fuel_tank_capacity_liters
    end_liters = end_fraction * fuel_tank_capacity_liters
    available = start_liters - end_liters

    if available < 0:
        raise ValueError("Fuel start level must be >= end level")

    total_distance = sum(distances_per_client)
    if total_distance == 0:
        raise ValueError("Total distance cannot be zero")

    per_client = []
    running_fuel = start_liters

    for dist in distances_per_client:
        proportion = dist / total_distance
        consumed = round(total_consumption_period_liters * proportion, 2)
        client_start = round(running_fuel, 2)
        client_end = round(running_fuel - consumed, 2)
        per_client.append({
            'fuel_start_liters': client_start,
            'fuel_end_liters': client_end,
            'fuel_consumed_liters': consumed,
        })
        running_fuel = client_end

    return {
        'start_liters': start_liters,
        'end_liters': end_liters,
        'available_consumption': available,
        'per_client': per_client,
    }
