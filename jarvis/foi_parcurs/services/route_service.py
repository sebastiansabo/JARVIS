"""Route assignment logic — TD/Comodat split and odometer distribution.

Key invariant: odometer is ALWAYS monotonically increasing across slots
(slot 1 has the lowest KM, last slot has the highest). Route types
(TD/Comodat) are randomly interleaved, not grouped.
"""

import random


def calculate_route_assignments(
    num_td: int,
    num_comodat: int,
    odometer_start: int,
    odometer_end: int,
) -> dict:
    num_clients = num_td + num_comodat
    if num_clients < 1:
        raise ValueError("Must have at least 1 client")

    total_km = odometer_end - odometer_start
    if total_km <= 0:
        raise ValueError("Odometer end must be greater than start")

    # ── 1. Calculate average km per client, then add ±20km jitter ──
    avg_km = total_km / num_clients
    min_km = max(1, int(avg_km * 0.3))  # floor at 30% of average or 1km

    if num_clients == 1:
        distances = [total_km]
    else:
        # Each client gets avg ± random(0..20) km
        jitter_range = min(20, int(avg_km * 0.4))  # cap jitter at 40% of avg
        raw = []
        for _ in range(num_clients):
            jitter = random.randint(-jitter_range, jitter_range)
            raw.append(max(min_km, int(avg_km + jitter)))

        # Scale to match exact total_km
        raw_sum = sum(raw)
        if raw_sum != total_km:
            # Proportionally scale
            factor = total_km / raw_sum
            raw = [max(min_km, int(d * factor)) for d in raw]

            # Fix rounding remainder
            leftover = total_km - sum(raw)
            indices = list(range(num_clients))
            random.shuffle(indices)
            for i in range(abs(leftover)):
                idx = indices[i % num_clients]
                raw[idx] += 1 if leftover > 0 else -1

        distances = raw

    # ── 2. Assign route types. Comodat is deprecated (2026-09): every slot is
    #       a Test Drive. num_comodat stays in the signature for UI/preview
    #       compatibility but no longer produces Comodat rows. ──
    types = ['TD'] * num_clients
    random.shuffle(types)

    # ── 3. Build slots with monotonically increasing odometer ──
    clients = []
    running_km = odometer_start
    for i in range(num_clients):
        km_start = running_km
        km_end = running_km + distances[i]
        clients.append({
            'slot': i + 1,
            'route_type': types[i],
            'km_start': km_start,
            'km_end': km_end,
            'distance_km': distances[i],
        })
        running_km = km_end

    return {
        'num_test_drives': num_td,
        'num_comadats': num_comodat,
        'total_distance_km': total_km,
        'distances': distances,
        'clients': clients,
    }
