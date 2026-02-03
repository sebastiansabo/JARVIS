"""
e-Factura Data Models

Data classes representing e-Factura entities for the connector.
These are used for internal data transfer, not ORM models.
"""

from dataclasses import dataclass, field
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List, Dict, Any
from enum import Enum

from .config import InvoiceDirection, EFacturaStatus, ArtifactType


@dataclass
class CompanyConnection:
    """
    Represents a company's connection to e-Factura system.
    Maps to efactura_company_connections table.
    """
    id: Optional[int] = None
    cif: str = ""  # Company tax ID (without RO prefix)
    display_name: str = ""
    environment: str = "test"  # test or production

    # Sync state
    last_sync_at: Optional[datetime] = None
    last_received_cursor: Optional[str] = None  # Cursor for pagination
    last_sent_cursor: Optional[str] = None

    # Status
    status: str = "active"  # active, paused, error, cert_expired
    status_message: Optional[str] = None

    # Configuration (JSON stored)
    config: Dict[str, Any] = field(default_factory=dict)

    # Certificate metadata (NOT the actual cert)
    cert_fingerprint: Optional[str] = None
    cert_expires_at: Optional[datetime] = None

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    def is_cert_expiring_soon(self, days: int = 30) -> bool:
        """Check if certificate is expiring within specified days."""
        if not self.cert_expires_at:
            return False
        return (self.cert_expires_at - datetime.now()).days < days


@dataclass
class Invoice:
    """
    Represents an e-Factura invoice.
    Maps to efactura_invoices table.
    """
    id: Optional[int] = None

    # Ownership
    cif_owner: str = ""  # Company that owns this invoice record
    direction: InvoiceDirection = InvoiceDirection.RECEIVED

    # Partner info
    partner_cif: str = ""
    partner_name: str = ""

    # Invoice details
    invoice_number: str = ""
    invoice_series: Optional[str] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None

    # Amounts (stored as Decimal for precision)
    total_amount: Decimal = Decimal("0.00")
    total_vat: Decimal = Decimal("0.00")
    total_without_vat: Decimal = Decimal("0.00")
    currency: str = "RON"

    # Status tracking
    status: EFacturaStatus = EFacturaStatus.PROCESSED

    # Timestamps
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None

    # Computed fields
    @property
    def full_invoice_number(self) -> str:
        """Get full invoice number with series if available."""
        if self.invoice_series:
            return f"{self.invoice_series}-{self.invoice_number}"
        return self.invoice_number


@dataclass
class InvoiceExternalRef:
    """
    External references from ANAF for an invoice.
    Maps to efactura_invoice_refs table.
    """
    id: Optional[int] = None
    invoice_id: int = 0

    # ANAF identifiers
    external_system: str = "anaf"
    message_id: str = ""  # ID mesaj from ANAF
    upload_id: Optional[str] = None  # ID incarcare
    download_id: Optional[str] = None  # ID descarcare

    # Integrity verification
    xml_hash: Optional[str] = None  # SHA256 of invoice XML
    signature_hash: Optional[str] = None  # Hash of signature

    # Raw response tracking
    raw_response_hash: Optional[str] = None

    created_at: Optional[datetime] = None


@dataclass
class InvoiceArtifact:
    """
    Stored file artifacts for an invoice.
    Maps to efactura_invoice_artifacts table.
    """
    id: Optional[int] = None
    invoice_id: int = 0

    artifact_type: ArtifactType = ArtifactType.ZIP
    storage_uri: str = ""  # Path in storage system

    # File metadata
    original_filename: Optional[str] = None
    mime_type: Optional[str] = None
    checksum: Optional[str] = None  # SHA256
    size_bytes: int = 0

    created_at: Optional[datetime] = None


@dataclass
class SyncRun:
    """
    Tracks a synchronization run.
    Maps to efactura_sync_runs table.
    """
    id: Optional[int] = None
    run_id: str = ""  # UUID for this run
    company_cif: str = ""

    # Timing
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None

    # Results
    success: bool = False
    direction: Optional[str] = None  # received, sent, or both

    # Counters
    messages_checked: int = 0
    invoices_fetched: int = 0
    invoices_created: int = 0
    invoices_updated: int = 0
    invoices_skipped: int = 0  # Already existed
    errors_count: int = 0

    # Cursor tracking
    cursor_before: Optional[str] = None
    cursor_after: Optional[str] = None

    # Summary
    error_summary: Optional[str] = None


@dataclass
class SyncError:
    """
    Tracks errors during synchronization.
    Maps to efactura_sync_errors table.
    """
    id: Optional[int] = None
    run_id: str = ""  # FK to SyncRun

    # Error context
    message_id: Optional[str] = None  # Related ANAF message ID
    invoice_ref: Optional[str] = None  # Invoice number if known

    # Error details
    error_type: str = ""  # AUTH, NETWORK, VALIDATION, API, PARSE
    error_code: Optional[str] = None
    error_message: str = ""

    # Debug info (hashed, never raw payloads)
    request_hash: Optional[str] = None
    response_hash: Optional[str] = None

    # Stack trace (truncated)
    stack_trace: Optional[str] = None

    created_at: Optional[datetime] = None

    # Whether this error is recoverable via retry
    is_retryable: bool = False


@dataclass
class ANAFMessage:
    """
    Represents a message from ANAF list response.
    This is a transient object, not stored directly.
    """
    id: str = ""  # Message ID
    cif: str = ""  # Company CIF
    upload_id: Optional[str] = None
    download_id: Optional[str] = None

    # Message details
    message_type: str = ""  # FACTURA, EROARE, etc.
    creation_date: Optional[datetime] = None

    # Status
    status: Optional[str] = None

    # Raw response for debugging
    raw_data: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_anaf_response(cls, data: Dict[str, Any]) -> 'ANAFMessage':
        """Create from ANAF API response."""
        return cls(
            id=str(data.get('id', '')),
            cif=str(data.get('cif', '')),
            upload_id=data.get('id_solicitare'),
            download_id=data.get('id'),
            message_type=data.get('tip', ''),
            creation_date=cls._parse_date(data.get('data_creare')),
            status=data.get('stare'),
            raw_data=data,
        )

    @staticmethod
    def _parse_date(date_str: Optional[str]) -> Optional[datetime]:
        """Parse ANAF date format."""
        if not date_str:
            return None
        try:
            # ANAF uses format: "202401151030" (YYYYMMDDHHmm)
            return datetime.strptime(date_str, "%Y%m%d%H%M")
        except ValueError:
            try:
                # Alternative format with separators
                return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
            except ValueError:
                return None


@dataclass
class InvoiceLineItem:
    """
    Represents a line item in an invoice.
    Extracted from XML, used for display/reports.
    """
    line_number: int = 0
    description: str = ""
    quantity: Decimal = Decimal("1")
    unit: str = "BUC"  # Bucata (piece)
    unit_price: Decimal = Decimal("0.00")

    # Amounts
    line_amount: Decimal = Decimal("0.00")
    vat_rate: Decimal = Decimal("19.00")
    vat_amount: Decimal = Decimal("0.00")

    # Item codes
    seller_item_id: Optional[str] = None
    buyer_item_id: Optional[str] = None

    # Classification
    commodity_code: Optional[str] = None  # NC code


@dataclass
class ParsedInvoice:
    """
    Full parsed invoice with all details.
    Extracted from XML content.
    """
    # Basic info
    invoice_number: str = ""
    invoice_series: Optional[str] = None
    issue_date: Optional[date] = None
    due_date: Optional[date] = None

    # Seller (supplier)
    seller_name: str = ""
    seller_cif: str = ""
    seller_address: Optional[str] = None
    seller_reg_number: Optional[str] = None  # J number

    # Buyer (customer)
    buyer_name: str = ""
    buyer_cif: str = ""
    buyer_address: Optional[str] = None

    # Amounts
    currency: str = "RON"
    total_without_vat: Decimal = Decimal("0.00")
    total_vat: Decimal = Decimal("0.00")
    total_amount: Decimal = Decimal("0.00")

    # VAT breakdown
    vat_breakdown: List[Dict[str, Decimal]] = field(default_factory=list)

    # Line items
    line_items: List[InvoiceLineItem] = field(default_factory=list)

    # Payment info
    payment_means: Optional[str] = None  # Bank transfer, etc.
    payment_terms: Optional[str] = None
    bank_account: Optional[str] = None

    # Notes
    invoice_note: Optional[str] = None

    # Original XML reference
    xml_hash: Optional[str] = None
