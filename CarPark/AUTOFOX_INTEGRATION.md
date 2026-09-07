# AutoFox → JARVIS photo integration

## Status (2026-09-07)
- AutoFox subscription paid. AutoFox (Customer Care) asked for "details/credentials so we can set up the connection with your CRM" → AutoFox **pushes** to JARVIS; JARVIS hosts the endpoint.
- Inbound webhook connector built, hardened and tested (17 tests green): `jarvis/carpark/connectors/autofox/` (`service.py`, `routes.py`), registered in `app.py`, tests `jarvis/tests/carpark/test_autofox_webhook.py`.
- **React settings UI shipped**: Settings → Connectors → **AutoFox (Vehicle Photos)** (`AutofoxSection` in `jarvis/frontend/src/pages/Settings/ConnectorsTab.tsx`, api module `jarvis/frontend/src/api/autofox.ts`). No more curl/Postman required for token setup.
- Branch: `feature/autofox-integration` (off `dev`).

## Endpoint contract JARVIS exposes
- `POST https://jarvis.autoworld.ro/autofox/webhook`
- Auth (any): `Authorization: Bearer <token>`, `X-API-Key`, `X-Autofox-Token`, Basic-auth password, or `?token=`. **The bearer token is the sole trusted gate.**
- Body: JSON with a VIN + image URL list (tolerant key detection: vin/VIN/fin/vehicle.vin…; images/photos/pictures/files/media…; url/href/downloadUrl…), or multipart `vin=<VIN>` + `files=`.
- Behaviour: resolve `carpark_vehicles.vin` → download (≤15 MB, **SSRF-guarded**) → `_compress_jpeg` (1600 px, q80) → private Spaces key `private/carpark/<vehicle_id>/autofox_<sha16>.jpg` → `carpark_vehicle_photos` (caption `autofox`, first photo primary only if vehicle had none). Idempotent by content hash. Raw payload (8 KB) logged to `connector_sync_log` so the real schema is captured on first delivery.
- Responses: 200 `{created, skipped_duplicates, errors}`, 401 bad token / disabled connector, 404 unknown VIN, 422 no VIN in payload, 503 Spaces disabled.

## Security hardening
- **SSRF guard** (`service._validate_url`): image URLs must be `http(s)` and resolve to a publicly-routable IP. Any private / loopback / link-local / reserved / multicast / unspecified address is rejected (blocks the cloud-metadata endpoint `169.254.169.254` and RFC1918 pivots); redirects are disabled (`allow_redirects=False`). A blocked URL is a per-image error, not a whole-delivery failure.
- **IP allowlist is advisory, not enforced.** `X-Forwarded-For` is caller-spoofable and JARVIS has no `ProxyFix` trusted-proxy config, so an IP check would be false assurance. A delivery from a non-allowlisted source is **logged** (`details.ip_allowed=false`, warning) but still accepted; the bearer token is what authenticates. The Settings UI labels the field as advisory.

## Admin API (session auth)
- `GET /autofox/api/config` — status, webhook URL, masked token, allowed_ips, replace_existing.
- `POST /autofox/api/config` `{rotate_token, allowed_ips, replace_existing, enabled}` — token returned in full only on generation, plus a curl example.
- `GET /autofox/api/logs` — recent deliveries (with `details.raw`).
- All exposed in the AutoFox settings section (generate/rotate token → one-time reveal + copy; edit allowed IPs; toggle replace-existing / enabled; expandable delivery log showing the raw payload).

## Go-live sequence
1. Merge `feature/autofox-integration` → deploy.
2. Settings → Connectors → AutoFox → **Generate Token**; copy the token (shown once) and the webhook URL.
3. Send AutoFox: webhook URL, token, auth header options, expected payload; ask for their egress IPs + payload spec.
4. AutoFox test push → open the delivery row's raw payload (or `GET /autofox/api/logs` `details.raw`) → adjust `extract_delivery()` key lists in `service.py` if their schema uses keys not covered.
5. Optionally set advisory `allowed_ips` and `replace_existing`.

## Open questions for AutoFox
Payload schema, URLs vs multipart, URL TTL, retry policy on non-2xx, egress IPs, whether they need a VIN→stock-number lookup endpoint from JARVIS (outbound endpoint NOT built — pending confirmation they need it).
