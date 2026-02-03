# RO e-Factura Connector

**Core connector** for ANAF's e-Factura (Romanian Electronic Invoice) system. This module is part of JARVIS Core and is available across all sections (Accounting, HR, etc.).

## Overview

The e-Factura connector:
- Authenticates with ANAF using X.509 digital certificates (TLS mutual auth)
- Fetches received and sent invoices via scheduled background sync
- Stores invoice metadata and artifacts (ZIP, XML, PDF) in the JARVIS database
- Provides API endpoints for listing, filtering, and downloading invoices
- Available as a core service to all JARVIS modules

## Location

```
jarvis/core/connectors/efactura/
```

This is a **core connector**, not section-specific. It can be used by:
- Accounting module (invoice management)
- HR module (expense tracking)
- Any future JARVIS section

## Usage

### Import in any JARVIS module

```python
# Import the blueprint
from core.connectors.efactura import efactura_bp

# Import specific components
from core.connectors.efactura.client import ANAFClient
from core.connectors.efactura.services import InvoiceService, CertificateAuthService
from core.connectors.efactura.repositories import InvoiceRepository
```

### Register in app.py

```python
from core.connectors import efactura_bp
app.register_blueprint(efactura_bp, url_prefix='/efactura')
```

## Prerequisites

### 1. ANAF Digital Certificate

1. **Obtain a qualified certificate** from an accredited certification authority
2. **Register the certificate** on ANAF SPV portal: https://www.anaf.ro/spv/
3. **Enable e-Factura access** for your company CIF
4. **Export as .p12/.pfx** file with private key

### 2. Environment Variables

```bash
# Certificate configuration
EFACTURA_CERT_PATH=/path/to/certificate.p12
EFACTURA_CERT_PASSWORD=your_cert_password

# Or base64-encoded for production
EFACTURA_CERT_BASE64=base64_encoded_certificate

# Environment
EFACTURA_ENVIRONMENT=test  # or 'production'

# Storage
EFACTURA_STORAGE_TYPE=local
EFACTURA_STORAGE_PATH=/path/to/artifacts
```

## Installation

### 1. Install Dependencies

Add to JARVIS `requirements.txt`:

```
cryptography>=41.0.0
```

### 2. Run Database Migration

```bash
psql $DATABASE_URL -f jarvis/core/connectors/efactura/migrations/001_create_efactura_tables.sql
```

## API Endpoints

All endpoints are prefixed with `/efactura`

### Company Connections
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/connections` | List all connections |
| POST | `/api/connections` | Create connection |
| DELETE | `/api/connections/<cif>` | Delete connection |

### Invoices
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/invoices?cif=<cif>` | List invoices |
| GET | `/api/invoices/<id>` | Get invoice details |
| GET | `/api/invoices/summary?cif=<cif>` | Get statistics |
| GET | `/api/invoices/unallocated` | List unallocated invoices |
| GET | `/api/invoices/unallocated/count` | Count for navigation badge |
| PUT | `/api/invoices/<id>/overrides` | Update invoice overrides (type, department, subdepartment) |
| PUT | `/api/invoices/bulk-overrides` | Bulk update overrides for multiple invoices |
| POST | `/api/invoices/send-to-module` | Send invoices to JARVIS Invoice Module |
| GET | `/api/invoices/<id>/pdf` | Export PDF from XML |

### Supplier Mappings
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/supplier-mappings` | List supplier mappings with types |
| POST | `/api/supplier-mappings` | Create supplier mapping |
| PUT | `/api/supplier-mappings/<id>` | Update supplier mapping |
| DELETE | `/api/supplier-mappings/<id>` | Delete supplier mapping |
| GET | `/api/partner-types` | List partner types (Service, Merchandise) |

### Sync Operations
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/sync/trigger` | Trigger manual sync |
| GET | `/api/sync/history` | Get sync history |

## Architecture

```
core/connectors/efactura/
├── __init__.py           # Blueprint registration
├── config.py             # Configuration & enums
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
│   └── sync_repo.py      # Sync tracking
├── migrations/
│   └── 001_create_*.sql  # Database schema
└── tests/
    ├── fixtures/         # Mock responses
    └── test_*.py         # Unit tests
```

## Rate Limiting

ANAF enforces **150 requests per hour** per certificate. The connector:
- Tracks requests in-memory
- Maintains a 10-request buffer
- Logs warnings when approaching limit

## Security

- Passwords/tokens are **never logged** (hashed instead)
- Temporary PEM files have **0600 permissions**
- Certificate content **never appears in errors**

## Testing

```bash
cd jarvis/core/connectors/efactura
python -m pytest tests/ -v
```

## Future Phases

- **Phase 2**: Background sync worker
- **Phase 3**: Enhanced XML parsing
- **Phase 4**: UI integration

## License

Proprietary - Part of JARVIS Enterprise Platform
