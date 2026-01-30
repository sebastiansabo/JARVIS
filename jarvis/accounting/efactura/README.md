# RO e-Factura Connector

Integration module for ANAF's e-Factura (Romanian Electronic Invoice) system. This connector enables JARVIS to automatically fetch, store, and manage electronic invoices received through the national e-Factura platform.

## Overview

The e-Factura connector:
- Authenticates with ANAF using X.509 digital certificates (TLS mutual auth)
- Fetches received and sent invoices via scheduled background sync
- Stores invoice metadata and artifacts (ZIP, XML, PDF) in the JARVIS database
- Provides API endpoints for listing, filtering, and downloading invoices
- Maintains audit trails for all sync operations

## Prerequisites

### 1. ANAF Digital Certificate

You need a qualified digital certificate registered with ANAF for e-Factura access:

1. **Obtain a qualified certificate** from an accredited certification authority (certSIGN, DigiSign, Trans Sped, etc.)
2. **Register the certificate** on the ANAF SPV (Virtual Private Space) portal: https://www.anaf.ro/spv/
3. **Enable e-Factura access** for your company CIF in the SPV portal
4. **Export the certificate** as a `.p12` or `.pfx` file with the private key

### 2. Company CIF Registration

Your company must be registered in the e-Factura system:
- CIF must be active in the ANAF database
- Company must be enrolled in e-Factura (automatic for B2G, optional for B2B)

### 3. Environment Setup

Required environment variables:

```bash
# Certificate configuration
EFACTURA_CERT_PATH=/path/to/certificate.p12
EFACTURA_CERT_PASSWORD=your_cert_password

# Or for production (base64-encoded cert)
EFACTURA_CERT_BASE64=base64_encoded_certificate

# Environment selection
EFACTURA_ENVIRONMENT=test  # or 'production'

# Database (uses JARVIS default)
DATABASE_URL=postgresql://...

# Storage configuration
EFACTURA_STORAGE_TYPE=local  # or 's3', 'gcs', 'drive'
EFACTURA_STORAGE_PATH=/path/to/artifacts

# Optional features
EFACTURA_ENABLE_SENT=true
EFACTURA_ENABLE_AUTO_SYNC=true
EFACTURA_ENABLE_NOTIFICATIONS=false
```

## Installation

### 1. Install Dependencies

Add to JARVIS `requirements.txt`:

```
cryptography>=41.0.0
requests>=2.31.0
```

### 2. Run Database Migration

```bash
# From JARVIS root directory
psql $DATABASE_URL -f jarvis/accounting/efactura/migrations/001_create_efactura_tables.sql
```

### 3. Register Blueprint

In `jarvis/app.py`, add:

```python
from accounting.efactura import efactura_bp
app.register_blueprint(efactura_bp, url_prefix='/efactura')
```

## Local Development

### Testing Without ANAF

The connector includes mock fixtures for local development:

```python
# Run tests with mocked responses
cd jarvis/accounting/efactura
python -m pytest tests/ -v
```

### Stub ANAF Client

For local development without a real certificate:

```python
from accounting.efactura.client import ANAFClient
from accounting.efactura.tests.fixtures import MOCK_LIST_RECEIVED_RESPONSE

# Create a mock client for testing
class MockANAFClient(ANAFClient):
    def list_received_messages(self, *args, **kwargs):
        return {
            'messages': MOCK_LIST_RECEIVED_RESPONSE['mesaje'],
            'has_more': False,
            'next_cursor': None,
        }
```

### Test Database Setup

```bash
# Create test tables
DATABASE_URL='postgresql://user@localhost/test_db' \
  psql -f jarvis/accounting/efactura/migrations/001_create_efactura_tables.sql
```

## Deployment

### DigitalOcean App Platform

1. **Add environment variables** in App Settings:
   - `EFACTURA_CERT_BASE64`: Base64-encoded .p12 file
   - `EFACTURA_CERT_PASSWORD`: Certificate password
   - `EFACTURA_ENVIRONMENT`: `production`

2. **Generate base64 certificate**:
   ```bash
   base64 -i certificate.p12 | tr -d '\n'
   ```

3. **Run migration** via console or deploy hook

### Docker

```dockerfile
# Certificate is passed via environment variable
ENV EFACTURA_CERT_BASE64=""
ENV EFACTURA_CERT_PASSWORD=""
```

## API Endpoints

### Company Connections

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/efactura/api/connections` | List all connections |
| GET | `/efactura/api/connections/<cif>` | Get connection details |
| POST | `/efactura/api/connections` | Create new connection |
| DELETE | `/efactura/api/connections/<cif>` | Delete connection |

### Invoices

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/efactura/api/invoices?cif=<cif>` | List invoices |
| GET | `/efactura/api/invoices/<id>` | Get invoice details |
| GET | `/efactura/api/invoices/<id>/download/<type>` | Download artifact |
| GET | `/efactura/api/invoices/summary?cif=<cif>` | Get summary stats |
| GET | `/efactura/api/invoices/unallocated` | List unallocated invoices |
| GET | `/efactura/api/invoices/unallocated/count` | Count for navigation badge |
| PUT | `/efactura/api/invoices/<id>/overrides` | Update invoice overrides |
| PUT | `/efactura/api/invoices/bulk-overrides` | Bulk update overrides |
| POST | `/efactura/api/invoices/send-to-module` | Send to JARVIS Invoice Module |
| GET | `/efactura/api/invoices/<id>/pdf` | Export PDF from XML |

### Supplier Mappings

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/efactura/api/supplier-mappings` | List supplier mappings with types |
| POST | `/efactura/api/supplier-mappings` | Create supplier mapping |
| PUT | `/efactura/api/supplier-mappings/<id>` | Update supplier mapping |
| DELETE | `/efactura/api/supplier-mappings/<id>` | Delete supplier mapping |
| GET | `/efactura/api/partner-types` | List partner types |

### Sync Operations

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/efactura/api/sync/trigger` | Trigger manual sync |
| GET | `/efactura/api/sync/history` | Get sync history |
| GET | `/efactura/api/sync/errors/<run_id>` | Get sync errors |
| GET | `/efactura/api/sync/stats` | Get error statistics |

## Rate Limiting

ANAF enforces strict rate limits:
- **150 requests per hour** per certificate
- The connector maintains a buffer of 10 requests
- Rate limit state is tracked in-memory per client instance

### Monitoring

```python
# Check current rate limit status
GET /efactura/api/rate-limit

# Response:
{
  "max_per_hour": 150,
  "remaining": 135,
  "requests_made": 15,
  "window_start": "2025-01-26T10:00:00"
}
```

## Sync Strategy

### Incremental Sync

The connector uses cursor-based pagination with a safety lookback:
1. Start from last successful cursor
2. Apply 7-day lookback window to catch missed messages
3. Process messages in chronological order
4. Update cursor after each successful batch

### Deduplication

Invoices are deduplicated by `(cif_owner, direction, message_id)`:
- Unique constraint in database
- Check before download to avoid unnecessary API calls
- Idempotent processing for retry safety

### Error Handling

All errors are:
1. Logged with structured metadata (no raw payloads)
2. Recorded in `efactura_sync_errors` table
3. Summarized in sync run record

Retryable errors:
- Network timeouts
- 5xx server errors
- Rate limit (with backoff)

Non-retryable errors:
- Authentication failures
- Validation errors
- 4xx client errors

## Known Limitations

### Message Retention

ANAF retains messages for a limited time:
- **60 days** for most message types
- Ensure sync runs at least weekly to avoid data loss

### Certificate Lifecycle

Certificates typically expire after 1-3 years:
- Monitor `cert_expires_at` in company connections
- Warning logged when < 30 days remaining
- Renew and re-upload before expiry

### XML Formats

The connector supports:
- UBL 2.1 (primary format)
- CII (Cross Industry Invoice)

Some edge cases in XML parsing may require updates.

## Troubleshooting

### Certificate Issues

```bash
# Verify certificate
openssl pkcs12 -info -in certificate.p12

# Check certificate expiry
openssl pkcs12 -in certificate.p12 -nokeys | openssl x509 -noout -dates
```

### Connection Issues

1. Verify CIF is registered in ANAF SPV
2. Check certificate is enabled for e-Factura
3. Verify network connectivity to ANAF servers
4. Check for IP-based restrictions (ANAF may block some cloud IPs)

### Sync Failures

Check sync history for patterns:
```sql
SELECT * FROM efactura_sync_runs
WHERE company_cif = '12345678'
ORDER BY started_at DESC
LIMIT 10;

SELECT error_type, COUNT(*)
FROM efactura_sync_errors
GROUP BY error_type;
```

## Architecture

```
efactura/
├── __init__.py           # Blueprint registration
├── config.py             # Configuration & constants
├── models.py             # Data classes
├── routes.py             # Flask API routes
├── client/
│   ├── anaf_client.py    # ANAF HTTP client
│   └── exceptions.py     # Custom exceptions
├── services/
│   ├── auth_service.py   # Certificate handling
│   └── invoice_service.py# Invoice processing
├── repositories/
│   ├── company_repo.py   # Company DB operations
│   ├── invoice_repo.py   # Invoice DB operations
│   └── sync_repo.py      # Sync tracking DB operations
├── migrations/
│   └── 001_create_*.sql  # Database schema
└── tests/
    ├── fixtures/         # Mock responses
    └── test_*.py         # Unit tests
```

## Future Phases

### Phase 2: Sync Worker
- Background job for hourly sync
- Idempotent sync logic
- Distributed lock for multi-instance

### Phase 3: XML Parsing Enhancements
- Full invoice detail extraction
- Line item parsing
- Payment information

### Phase 4: UI Integration
- JARVIS dashboard widget
- Invoice browser with filters
- Manual sync trigger button
- Certificate management UI

## Contributing

1. Write tests for new functionality
2. Follow JARVIS coding conventions
3. Never log sensitive data (passwords, tokens, cert content)
4. Update this README for significant changes

## License

Proprietary - Part of JARVIS Enterprise Platform
