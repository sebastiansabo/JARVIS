"""Pydantic v2 schemas for the Voucher module."""
from __future__ import annotations

import re
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class VoucherCreate(BaseModel):
    client_name: str
    contract_number: str
    car_vin: str
    validity_months: int
    voucher_type: str
    value_lei: Optional[Decimal] = None
    discount_code: Optional[str] = None
    discount_percentage: Optional[Decimal] = None
    service_items: Optional[list[str]] = None
    approver_user_id: Optional[int] = None
    notes: Optional[str] = None
    start_date: Optional[date] = None
    client_email: Optional[str] = None
    client_cif: Optional[str] = None

    @field_validator('client_email')
    @classmethod
    def validate_client_email(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip()
        if not v:
            return None
        if '@' not in v:
            raise ValueError('client_email must be a valid email address')
        return v

    @field_validator('client_cif')
    @classmethod
    def validate_client_cif(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        v = v.strip().upper()
        return v or None

    @field_validator('car_vin')
    @classmethod
    def validate_vin(cls, v: str) -> str:
        v = v.strip().upper()
        if not re.fullmatch(r'[A-Z0-9]{17}', v):
            raise ValueError('VIN must be exactly 17 alphanumeric characters')
        return v

    @field_validator('validity_months')
    @classmethod
    def validate_validity(cls, v: int) -> int:
        if v not in (1, 3, 6, 12, 24):
            raise ValueError('validity_months must be 1, 3, 6, 12, or 24')
        return v

    @field_validator('voucher_type')
    @classmethod
    def validate_type(cls, v: str) -> str:
        allowed = ('value', 'accessory_discount_code', 'accessory_percentage', 'service_items')
        if v not in allowed:
            raise ValueError(f'voucher_type must be one of {allowed}')
        return v

    @field_validator('discount_percentage')
    @classmethod
    def validate_percentage(cls, v: Optional[Decimal]) -> Optional[Decimal]:
        if v is not None and (v < 0 or v > 100):
            raise ValueError('discount_percentage must be between 0 and 100')
        return v

    @model_validator(mode='after')
    def validate_type_fields(self):
        """Ensure exactly one type-specific field is populated, matching voucher_type."""
        vt = self.voucher_type
        fields_map = {
            'value': ('value_lei', self.value_lei),
            'accessory_discount_code': ('discount_code', self.discount_code),
            'accessory_percentage': ('discount_percentage', self.discount_percentage),
            'service_items': ('service_items', self.service_items),
        }
        field_name, field_val = fields_map[vt]
        if field_val is None or (isinstance(field_val, list) and len(field_val) == 0):
            raise ValueError(f'{field_name} is required when voucher_type is {vt}')

        for other_type, (other_name, other_val) in fields_map.items():
            if other_type != vt and other_val is not None:
                raise ValueError(f'{other_name} must be null when voucher_type is {vt}')

        return self


class VoucherRead(BaseModel):
    id: int
    company_id: int
    voucher_code: str
    client_name: str
    contract_number: str
    car_vin: str
    validity_months: int
    expires_at: Optional[date] = None
    issued_at: Optional[date] = None
    issued_by_user_id: int
    issued_by_name: Optional[str] = None
    voucher_type: str
    value_lei: Optional[Decimal] = None
    discount_code: Optional[str] = None
    discount_percentage: Optional[Decimal] = None
    service_items: Optional[list[str]] = None
    status: str
    approver_user_id: Optional[int] = None
    approver_name: Optional[str] = None
    approval_request_id: Optional[int] = None
    redeemed_at: Optional[datetime] = None
    redeemed_by_user_id: Optional[int] = None
    redeemed_by_name: Optional[str] = None
    redemption_notes: Optional[str] = None
    notes: Optional[str] = None
    start_date: Optional[date] = None
    client_email: Optional[str] = None
    client_cif: Optional[str] = None
    days_remaining: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class VoucherListItem(BaseModel):
    id: int
    voucher_code: str
    client_name: str
    contract_number: str
    car_vin: str
    voucher_type: str
    benefit_display: str
    issued_at: Optional[date] = None
    expires_at: Optional[date] = None
    days_remaining: Optional[int] = None
    status: str
    issued_by_name: Optional[str] = None


class VoucherRedeem(BaseModel):
    redemption_notes: Optional[str] = None
