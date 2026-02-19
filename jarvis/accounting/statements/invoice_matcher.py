"""
Invoice matching logic for bank statement transactions.

Matches transactions to invoices using a 3-layer approach:
1. Rule-based matching (supplier + amount)
2. Heuristic scoring (date proximity, amount variance)
3. AI fallback (Claude semantic analysis)
"""
import json
import logging
import os
from datetime import datetime, timedelta
from difflib import SequenceMatcher

from ai_agent.providers.base_provider import BaseProvider

logger = logging.getLogger('jarvis.statements.invoice_matcher')

# Matching thresholds
AUTO_ACCEPT_THRESHOLD = 0.9  # Auto-link if confidence >= this
SUGGESTION_THRESHOLD = 0.5   # Suggest if confidence >= this (lowered for exact amount matching)
AMOUNT_TOLERANCE_PERCENT = 0.1  # 0.1% tolerance for exact match (99.9%)
MAX_DATE_DIFFERENCE_DAYS = 60  # Max days between invoice and transaction

# Scoring weights - HEAVILY prioritize exact amount match
# Exact amount (0.1%) = 90 points = 90% confidence alone
SCORE_EXACT_AMOUNT = 90
SCORE_CLOSE_AMOUNT = 40  # Within 1%
SCORE_MEDIUM_AMOUNT = 20  # Within 5%
SCORE_DATE_SAME_WEEK = 5
SCORE_DATE_SAME_MONTH = 3
SCORE_DATE_WITHIN_60_DAYS = 2
SCORE_SUPPLIER_EXACT = 5
SCORE_SUPPLIER_SIMILAR = 2


def normalize_amount(amount: float) -> float:
    """Normalize amount to positive value for comparison."""
    return abs(amount) if amount else 0


def amounts_match(txn_amount: float, inv_amount: float, tolerance_percent: float = AMOUNT_TOLERANCE_PERCENT) -> bool:
    """Check if two amounts match within tolerance."""
    txn_abs = normalize_amount(txn_amount)
    inv_abs = normalize_amount(inv_amount)

    if inv_abs == 0:
        return txn_abs == 0

    diff_percent = abs(txn_abs - inv_abs) / inv_abs * 100
    return diff_percent <= tolerance_percent


def calculate_amount_score(txn_amount: float, inv_amount: float) -> int:
    """
    Calculate score based on amount match.

    Returns:
        - 90: Exact match (within 0.1% - 99.9% match)
        - 40: Close match (within 1%)
        - 20: Medium match (within 5%)
        - 0: No match
    """
    txn_abs = normalize_amount(txn_amount)
    inv_abs = normalize_amount(inv_amount)

    if inv_abs == 0:
        return SCORE_EXACT_AMOUNT if txn_abs == 0 else 0

    diff_percent = abs(txn_abs - inv_abs) / inv_abs * 100

    if diff_percent <= 0.1:  # 99.9% match
        return SCORE_EXACT_AMOUNT
    elif diff_percent <= 1:
        return SCORE_CLOSE_AMOUNT
    elif diff_percent <= 5:
        return SCORE_MEDIUM_AMOUNT
    return 0


def calculate_date_score(txn_date, inv_date) -> int:
    """
    Calculate score based on date proximity.
    Transaction date should be >= invoice date (payment after invoice).

    Returns:
        - 30: Same week
        - 20: Same month
        - 10: Within 60 days
        - 0: Beyond 60 days or transaction before invoice
    """
    if not txn_date or not inv_date:
        return 0

    # Normalize to date objects for comparison
    if isinstance(txn_date, str):
        txn_date = datetime.fromisoformat(txn_date).date() if 'T' in txn_date else datetime.strptime(txn_date, '%Y-%m-%d').date()
    elif isinstance(txn_date, datetime):
        txn_date = txn_date.date()
    # If already a date object, keep as is

    if isinstance(inv_date, str):
        inv_date = datetime.fromisoformat(inv_date).date() if 'T' in inv_date else datetime.strptime(inv_date, '%Y-%m-%d').date()
    elif isinstance(inv_date, datetime):
        inv_date = inv_date.date()
    # If already a date object, keep as is

    # Transaction should be after or on same day as invoice
    if txn_date < inv_date:
        return 0

    diff_days = (txn_date - inv_date).days

    if diff_days <= 7:
        return SCORE_DATE_SAME_WEEK
    elif diff_days <= 30:
        return SCORE_DATE_SAME_MONTH
    elif diff_days <= MAX_DATE_DIFFERENCE_DAYS:
        return SCORE_DATE_WITHIN_60_DAYS
    return 0


def calculate_supplier_score(txn_supplier: str, inv_supplier: str) -> int:
    """
    Calculate score based on supplier name match.

    Returns:
        - 20: Exact match
        - 10: Similar (>80% similarity)
        - 0: No match
    """
    if not txn_supplier or not inv_supplier:
        return 0

    txn_lower = txn_supplier.lower().strip()
    inv_lower = inv_supplier.lower().strip()

    if txn_lower == inv_lower:
        return SCORE_SUPPLIER_EXACT

    # Calculate similarity ratio
    similarity = SequenceMatcher(None, txn_lower, inv_lower).ratio()

    if similarity >= 0.8:
        return SCORE_SUPPLIER_SIMILAR

    return 0


def find_invoice_candidates(transaction: dict, invoices: list) -> list[dict]:
    """
    Find potential invoice matches for a transaction.

    Args:
        transaction: Dict with amount, transaction_date, matched_supplier, currency
        invoices: List of invoice dicts with invoice_value, invoice_date, supplier, etc.

    Returns:
        List of candidates sorted by score:
        [{'invoice': {...}, 'score': 0.95, 'reasons': ['exact_amount', 'same_supplier']}]
    """
    candidates = []
    txn_amount = normalize_amount(transaction.get('amount', 0))
    txn_date = transaction.get('transaction_date')
    txn_supplier = transaction.get('matched_supplier')
    txn_currency = transaction.get('currency', 'RON')

    for invoice in invoices:
        # Skip already matched invoices (check by payment_status or other criteria)
        # For now, consider all invoices as candidates

        # Get invoice amount in same currency or use value_ron for comparison
        if txn_currency == 'RON':
            inv_amount = invoice.get('value_ron') or invoice.get('invoice_value', 0)
        elif txn_currency == 'EUR':
            inv_amount = invoice.get('value_eur') or invoice.get('invoice_value', 0)
        else:
            inv_amount = invoice.get('invoice_value', 0)

        inv_amount = normalize_amount(inv_amount)
        inv_date = invoice.get('invoice_date')
        inv_supplier = invoice.get('supplier')

        # Calculate scores
        amount_score = calculate_amount_score(txn_amount, inv_amount)
        date_score = calculate_date_score(txn_date, inv_date)
        supplier_score = calculate_supplier_score(txn_supplier, inv_supplier)

        total_score = amount_score + date_score + supplier_score

        # Only consider if there's at least some match
        if total_score > 0:
            reasons = []
            if amount_score >= SCORE_EXACT_AMOUNT:
                reasons.append('Exact amount match')
            elif amount_score >= SCORE_CLOSE_AMOUNT:
                reasons.append('Amount within 5%')
            elif amount_score > 0:
                reasons.append('Amount within 10%')

            if date_score >= SCORE_DATE_SAME_WEEK:
                reasons.append('Date within same week')
            elif date_score >= SCORE_DATE_SAME_MONTH:
                reasons.append('Date within same month')
            elif date_score > 0:
                reasons.append('Date within 60 days')

            if supplier_score >= SCORE_SUPPLIER_EXACT:
                reasons.append('Exact supplier match')
            elif supplier_score > 0:
                reasons.append('Similar supplier name')

            # Convert score to confidence (0-1)
            max_possible = SCORE_EXACT_AMOUNT + SCORE_DATE_SAME_WEEK + SCORE_SUPPLIER_EXACT
            confidence = total_score / max_possible

            candidates.append({
                'invoice': invoice,
                'invoice_id': invoice.get('id'),
                'score': total_score,
                'confidence': round(confidence, 2),
                'reasons': reasons,
                'amount_score': amount_score,
                'date_score': date_score,
                'supplier_score': supplier_score
            })

    # Sort by score descending
    candidates.sort(key=lambda x: x['score'], reverse=True)

    return candidates


def match_by_rules(transaction: dict, invoices: list) -> dict | None:
    """
    Attempt exact rule-based match: same supplier + amount within 1% + valid date.

    Returns:
        Best match dict or None if no match found.
    """
    candidates = find_invoice_candidates(transaction, invoices)

    for candidate in candidates:
        # Rule-based match requires all three criteria
        if (candidate['amount_score'] >= SCORE_EXACT_AMOUNT and
            candidate['date_score'] > 0 and
            candidate['supplier_score'] >= SCORE_SUPPLIER_EXACT):

            return {
                'invoice_id': candidate['invoice_id'],
                'confidence': candidate['confidence'],
                'method': 'rule',
                'reasons': candidate['reasons']
            }

    return None


def score_candidates(transaction: dict, invoices: list, limit: int = 3) -> list[dict]:
    """
    Score all potential matches and return top candidates.

    Args:
        transaction: Transaction dict
        invoices: List of invoice dicts
        limit: Max number of candidates to return

    Returns:
        Top scored candidates with details.
    """
    candidates = find_invoice_candidates(transaction, invoices)

    # Return top N candidates
    return candidates[:limit]


def match_with_ai(transaction: dict, candidates: list, use_cache: bool = True) -> dict:
    """
    Use Claude AI to analyze transaction and suggest best invoice match.

    Args:
        transaction: Transaction dict with description, amount, date, etc.
        candidates: List of candidate invoices from heuristic scoring
        use_cache: Whether to use cached results (not implemented yet)

    Returns:
        Match result with invoice_id, confidence, reasoning, and alternatives.
    """
    import anthropic

    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        logger.warning('ANTHROPIC_API_KEY not set, skipping AI matching')
        return {
            'invoice_id': None,
            'confidence': 0,
            'method': 'ai',
            'error': 'API key not configured'
        }

    if not candidates:
        return {
            'invoice_id': None,
            'confidence': 0,
            'method': 'ai',
            'reasoning': 'No candidates to analyze'
        }

    # Prepare candidate invoices for the prompt
    invoices_for_prompt = []
    for c in candidates[:5]:  # Max 5 candidates for AI
        inv = c['invoice']
        invoices_for_prompt.append({
            'invoice_id': inv.get('id'),
            'invoice_number': inv.get('invoice_number'),
            'supplier': inv.get('supplier'),
            'amount': inv.get('invoice_value'),
            'currency': inv.get('currency'),
            'date': str(inv.get('invoice_date')),
            'heuristic_score': c['score'],
            'reasons': c['reasons']
        })

    prompt = f"""Analyze this bank transaction and determine which invoice it corresponds to.

TRANSACTION:
- Date: {transaction.get('transaction_date')}
- Amount: {abs(transaction.get('amount', 0))} {transaction.get('currency', 'RON')}
- Description: {transaction.get('description', '')}
- Vendor: {transaction.get('vendor_name', '')}
- Matched Supplier: {transaction.get('matched_supplier', '')}

CANDIDATE INVOICES:
{json.dumps(invoices_for_prompt, indent=2)}

Return a JSON object with your analysis:
{{
    "best_match_invoice_id": <invoice_id or null>,
    "confidence": <0.0-1.0>,
    "reasoning": "<brief explanation>",
    "alternative_matches": [
        {{"invoice_id": <id>, "confidence": <score>, "reason": "<why>"}}
    ]
}}

Consider:
- Amount should match (allow small variance for fees/rounding)
- Transaction date is typically AFTER invoice date (payment delay)
- Supplier/vendor names may not match exactly (FACEBK = Meta, GOOGLE*ADS = Google Ads)
- Currency conversions may affect amounts
- If amounts are significantly different, they probably don't match

Return ONLY valid JSON, no other text."""

    try:
        client = anthropic.Anthropic(api_key=api_key)

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text
        result = BaseProvider._extract_json(response_text)

        return {
            'invoice_id': result.get('best_match_invoice_id'),
            'confidence': result.get('confidence', 0),
            'method': 'ai',
            'reasoning': result.get('reasoning'),
            'alternatives': result.get('alternative_matches', [])
        }

    except (json.JSONDecodeError, ValueError) as e:
        logger.error(f'AI matching JSON parse error: {e}')
        return {
            'invoice_id': None,
            'confidence': 0,
            'method': 'ai',
            'error': f'JSON parse error: {str(e)}'
        }
    except Exception as e:
        logger.exception(f'AI matching error: {e}')
        return {
            'invoice_id': None,
            'confidence': 0,
            'method': 'ai',
            'error': str(e)
        }


def auto_match_transaction(transaction: dict, invoices: list, use_ai: bool = True) -> dict:
    """
    Match a single transaction to an invoice using the 3-layer approach.

    Args:
        transaction: Transaction dict
        invoices: List of candidate invoices
        use_ai: Whether to use AI fallback

    Returns:
        Match result dict with:
        - invoice_id: Matched invoice ID (or None)
        - suggested_invoice_id: Suggested invoice for review (or None)
        - confidence: 0.0-1.0 confidence score
        - method: 'rule', 'heuristic', 'ai', or None
        - auto_accepted: Whether match was auto-accepted
        - reasons: List of match reasons
    """
    # Layer 1: Rule-based matching
    rule_match = match_by_rules(transaction, invoices)
    if rule_match and rule_match['confidence'] >= AUTO_ACCEPT_THRESHOLD:
        return {
            'invoice_id': rule_match['invoice_id'],
            'suggested_invoice_id': None,
            'confidence': rule_match['confidence'],
            'method': 'rule',
            'auto_accepted': True,
            'reasons': rule_match['reasons']
        }

    # Layer 2: Heuristic scoring
    candidates = score_candidates(transaction, invoices)

    if candidates:
        best = candidates[0]

        # If high confidence, auto-accept
        if best['confidence'] >= AUTO_ACCEPT_THRESHOLD:
            return {
                'invoice_id': best['invoice_id'],
                'suggested_invoice_id': None,
                'confidence': best['confidence'],
                'method': 'heuristic',
                'auto_accepted': True,
                'reasons': best['reasons']
            }

        # If medium confidence, suggest for review
        if best['confidence'] >= SUGGESTION_THRESHOLD:
            return {
                'invoice_id': None,
                'suggested_invoice_id': best['invoice_id'],
                'confidence': best['confidence'],
                'method': 'heuristic',
                'auto_accepted': False,
                'reasons': best['reasons']
            }

    # Layer 3: AI fallback
    if use_ai and candidates:
        ai_result = match_with_ai(transaction, candidates)

        if ai_result.get('invoice_id') and ai_result.get('confidence', 0) >= AUTO_ACCEPT_THRESHOLD:
            return {
                'invoice_id': ai_result['invoice_id'],
                'suggested_invoice_id': None,
                'confidence': ai_result['confidence'],
                'method': 'ai',
                'auto_accepted': True,
                'reasons': [ai_result.get('reasoning', 'AI matched')]
            }
        elif ai_result.get('invoice_id') and ai_result.get('confidence', 0) >= SUGGESTION_THRESHOLD:
            return {
                'invoice_id': None,
                'suggested_invoice_id': ai_result['invoice_id'],
                'confidence': ai_result['confidence'],
                'method': 'ai',
                'auto_accepted': False,
                'reasons': [ai_result.get('reasoning', 'AI suggested')]
            }

    # No match found
    return {
        'invoice_id': None,
        'suggested_invoice_id': candidates[0]['invoice_id'] if candidates else None,
        'confidence': candidates[0]['confidence'] if candidates else 0,
        'method': None,
        'auto_accepted': False,
        'reasons': ['No confident match found']
    }


def auto_match_transactions(transactions: list, invoices: list, use_ai: bool = True,
                           min_confidence: float = SUGGESTION_THRESHOLD) -> dict:
    """
    Match multiple transactions to invoices.

    Args:
        transactions: List of transaction dicts
        invoices: List of invoice dicts
        use_ai: Whether to enable AI fallback
        min_confidence: Minimum confidence for suggestions

    Returns:
        Summary dict with:
        - matched: Count of auto-matched transactions
        - suggested: Count of suggestions requiring review
        - unmatched: Count of unmatched transactions
        - results: List of individual match results
    """
    results = []
    matched_count = 0
    suggested_count = 0
    unmatched_count = 0

    for txn in transactions:
        # Skip already resolved transactions
        if txn.get('status') == 'resolved' or txn.get('invoice_id'):
            continue

        # Skip ignored transactions
        if txn.get('status') == 'ignored':
            continue

        result = auto_match_transaction(txn, invoices, use_ai=use_ai)
        result['transaction_id'] = txn.get('id')

        if result['auto_accepted'] and result['invoice_id']:
            matched_count += 1
        elif result['suggested_invoice_id']:
            suggested_count += 1
        else:
            unmatched_count += 1

        results.append(result)

    return {
        'matched': matched_count,
        'suggested': suggested_count,
        'unmatched': unmatched_count,
        'results': results
    }
