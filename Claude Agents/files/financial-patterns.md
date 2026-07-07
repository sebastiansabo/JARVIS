# Financial Accounting Patterns

## Double-Entry Bookkeeping
Every financial event creates a journal entry with balanced debit and credit lines.

```python
# Standard patterns
# Purchase received:
debit:  expense_account    credit: accounts_payable
# Payment made:
debit:  accounts_payable   credit: bank_account
# Invoice sent:
debit:  accounts_receivable  credit: revenue_account
# Payment received:
debit:  bank_account       credit: accounts_receivable
```

## Romanian Chart of Accounts (Planul de Conturi)
```
Class 1: Capital accounts (10xx-16xx)
Class 2: Fixed assets (20xx-28xx)
Class 3: Inventory (30xx-39xx)
Class 4: Third parties - receivables/payables (40xx-47xx)
Class 5: Treasury - bank/cash (51xx-53xx)
Class 6: Expenses (60xx-69xx)
Class 7: Revenue (70xx-78xx)
```

## VAT Handling
```python
STANDARD_VAT = Decimal("0.19")   # 19% standard
REDUCED_VAT = Decimal("0.09")    # 9% food, hotels, etc.
SPECIAL_VAT = Decimal("0.05")    # 5% housing

# VAT calculation — always from net, never reverse-calculate
vat_amount = net_amount * vat_rate
gross_amount = net_amount + vat_amount
```

## Currency Handling
- All amounts stored as `Decimal` with 2 decimal places for EUR/RON
- Crypto amounts: up to 8 decimal places
- Exchange rates: 6 decimal places
- Rounding: ROUND_HALF_UP for Romanian accounting
- Multi-currency: store original_amount + original_currency + exchange_rate + eur_amount

## Fiscal Period Rules
- Fiscal year: January 1 – December 31 (Romania)
- Monthly VAT declaration (D300) by 25th of following month
- Annual financial statements by March 31
- Closed periods: no modifications allowed after period close (use reversals)

## Transaction States
```
PENDING → POSTED → [REVERSED]
                 → [ARCHIVED]
```
Never delete. Only reverse or archive.

## Invoice States
```
DRAFT → SENT → [PAID] → [ARCHIVED]
            → [OVERDUE] → [PAID]
            → [CANCELLED] (creates reversal)
```

## Reconciliation Rules
1. Exact match: amount + date + reference → auto-reconcile
2. Fuzzy match: amount + date range (±3 days) + vendor → suggest
3. Split match: one bank transaction → multiple invoices (sum must equal)
4. Unmatched: flag for manual review after 30 days
