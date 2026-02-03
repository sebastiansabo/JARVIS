================================================================================
JARVIS AI AGENT - DIAGNOSTICS & DEBUGGING MODULE
================================================================================

Enhanced AI Agent with System Weakness Detection, Performance Monitoring,
Data Integrity Checks, and Automated Debugging.

SPECIFICATION:
==============

## Overview

The AI Agent includes a **Diagnostics Engine** that:
1. **Identifies system weaknesses** (data quality, unmatched transactions, etc.)
2. **Detects performance bottlenecks** (slow queries, high token usage)
3. **Performs data integrity checks** (GL balance, invoice reconciliation)
4. **Runs automated debugging** (finds root causes of issues)
5. **Provides health reports** (system status dashboard)
6. **Alerts on anomalies** (unusual patterns, data drift)

### Core Principle
"Not just answer questions - identify and fix problems proactively"

## Module: DiagnosticsService

Purpose: Comprehensive system health and weakness detection

### 1. Service: SystemHealthService

Purpose: Overall system diagnostics

run_full_system_diagnostic(company_id) → HealthReport:
  Input: company_id
  Process:
    1. Run 10 diagnostic checks:
       ✓ GL Balance Check
       ✓ Invoice Reconciliation Check
       ✓ Transaction Matching Check
       ✓ Data Completeness Check
       ✓ Performance Check
       ✓ Rate Limit Check
       ✓ Cost Efficiency Check
       ✓ Data Quality Check
       ✓ Permission Check
       ✓ Anomaly Detection
    
    2. Score each check:
       PASS (100) = no issues
       WARNING (50-99) = minor issues
       CRITICAL (0-49) = serious problems
    
    3. Aggregate results
    4. Return health report
  
  Returns: HealthReport {
    overall_health_score: 0-100,
    checks: [
      {check_name, status, score, details, recommendations}
    ],
    weak_points: [...],
    recommendations: [...],
    timestamp: now()
  }
  
  Example Output:
  ```
  SYSTEM HEALTH REPORT
  ═══════════════════════════════════════════════════════════
  Overall Health Score: 72/100 ⚠️  NEEDS ATTENTION
  
  ✅ PASS: GL Balance Check (100/100)
     Your GL is perfectly balanced (debit = credit)
  
  ⚠️  WARNING: Invoice Reconciliation (60/100)
     - 12 invoices unmatched to transactions
     - €5,000 in unmatched items
     - Recommendation: Run reconciliation
  
  ❌ CRITICAL: Performance Issue (40/100)
     - Average query time: 3.2 seconds (target: 1s)
     - Indexing needed on: invoice.vendor_id, transaction.date
     - Recommendation: Run DB optimization
  
  ⚠️  WARNING: Data Quality (65/100)
     - 3 invoices missing vendor_id
     - 15 transactions with description='UNKNOWN'
     - Recommendation: Cleanse data
  
  Weak Points:
  1. Reconciliation not current (last run: 5 days ago)
  2. Missing indices on frequently queried columns
  3. 18 incomplete records found
  
  Recommendations:
  → Run Invoice Reconciliation NOW
  → Create indices on vendor_id, customer_id, date
  → Clean up 18 incomplete records
  → Review unmatched transactions
  ```

### 2. Service: DataIntegrityService

Purpose: Detect data quality issues and inconsistencies

check_gl_balance(company_id, account_id=None) → BalanceCheckResult:
  Input: company_id, account_id (optional)
  Process:
    1. Query all GL postings for company
    2. Calculate total debits
    3. Calculate total credits
    4. Check: debits == credits
    5. For each account: assets + liabilities + equity balance
    6. Return results
  Returns: {
    is_balanced: bool,
    total_debits: Decimal,
    total_credits: Decimal,
    variance: Decimal,
    unbalanced_accounts: [...]
  }
  Alert: If variance > 0:
    "⚠️  CRITICAL: GL out of balance by €{variance}
     This should NEVER happen. Investigate immediately."

check_invoice_reconciliation(company_id) → ReconciliationStatus:
  Input: company_id
  Process:
    1. Query all invoices
    2. Count matched to transactions
    3. Count unmatched
    4. Sum unmatched amounts
    5. Identify old unmatched (> 90 days)
    6. Return status
  Returns: {
    total_invoices: int,
    matched_count: int,
    unmatched_count: int,
    unmatched_amount: Decimal,
    old_unmatched_count: int,
    old_unmatched_amount: Decimal,
    match_percentage: Decimal(5, 2),
    status: HEALTHY | WARNING | CRITICAL
  }
  Alert: If unmatched_count > 20:
    "⚠️  WARNING: {n} invoices unmatched totaling €{amount}
     Run reconciliation to clear these items."

check_transaction_matching(company_id) → MatchingStatus:
  Input: company_id
  Process:
    1. Query all transactions
    2. Count matched to invoices
    3. Count unmatched
    4. Sum unmatched amounts
    5. Identify suspicious unmatched (> €5,000)
    6. Return status
  Returns: {
    total_transactions: int,
    matched_count: int,
    unmatched_count: int,
    unmatched_amount: Decimal,
    suspicious_unmatched: [...],
    match_percentage: Decimal(5, 2),
    status: HEALTHY | WARNING | CRITICAL
  }
  Alert: If unmatched_amount > €10,000:
    "⚠️  WARNING: €{amount} in unmatched transactions
     Investigate large unmatched items."

check_data_completeness(company_id) → CompletenessReport:
  Input: company_id
  Process:
    1. Check Invoice records:
       - Missing vendor_id: count
       - Missing amount: count
       - Missing date: count
    2. Check Transaction records:
       - Missing description: count
       - Missing amount: count
       - Missing date: count
    3. Check GLPosting records:
       - Missing account_id: count
       - Missing amount: count
    4. Calculate completeness percentage
    5. Return report
  Returns: {
    invoice_completeness: Decimal(5, 2),
    transaction_completeness: Decimal(5, 2),
    gl_posting_completeness: Decimal(5, 2),
    missing_records: [
      {table, count, fields_missing}
    ],
    overall_completeness: Decimal(5, 2)
  }
  Alert: If overall_completeness < 95%:
    "⚠️  WARNING: {n} incomplete records found
     Missing critical fields: {fields}
     Data Quality: {score}%"

check_for_duplicates(company_id) → DuplicateReport:
  Input: company_id
  Process:
    1. Find duplicate invoices:
       - Same vendor, amount, date
    2. Find duplicate transactions:
       - Same amount, date, description
    3. Count duplicates
    4. Return report
  Returns: {
    duplicate_invoices: [...],
    duplicate_transactions: [...],
    total_duplicates: int,
    status: HEALTHY | WARNING
  }
  Alert: If total_duplicates > 0:
    "⚠️  WARNING: {n} duplicate records found
     These may indicate data entry errors or import issues."

### 3. Service: PerformanceMonitoringService

Purpose: Track performance and identify bottlenecks

monitor_query_performance(company_id, days=7) → PerformanceReport:
  Input: company_id, lookback period
  Process:
    1. Query all database queries for period
    2. Measure execution time
    3. Identify slow queries (> 2 seconds)
    4. Identify missing indices
    5. Calculate averages
    6. Return report
  Returns: {
    avg_query_time_ms: int,
    slow_queries: [
      {query, execution_time, count, missing_indices}
    ],
    queries_without_indices: [
      {table, column, estimated_improvement}
    ],
    recommendation: string,
    status: HEALTHY | WARNING | CRITICAL
  }
  Example Slow Query:
    "SELECT * FROM invoices WHERE vendor_id = ?
     Execution time: 3.2 seconds
     Missing index: invoices.vendor_id
     Estimated improvement: 50x faster with index"

monitor_llm_performance(company_id, provider=None) → LLMPerformanceReport:
  Input: company_id, provider (optional)
  Process:
    1. Query RAGUsageLog for period
    2. Calculate statistics:
       - Avg latency per provider
       - Token usage trends
       - Cost per request
       - Error rate
    3. Identify inefficiencies:
       - Excessive token usage
       - High error rate
       - Slow providers
    4. Return report
  Returns: {
    by_provider: {
      provider: {
        avg_latency_ms: int,
        total_tokens: int,
        total_cost: Decimal,
        error_rate: Decimal(5, 2),
        efficiency_score: 0-100
      }
    },
    slowest_provider: string,
    most_expensive_provider: string,
    most_reliable_provider: string,
    recommendations: [...]
  }
  Example:
    "Claude performance:
     - Avg latency: 2.3 seconds ✓ GOOD
     - Total tokens: 1.2M
     - Total cost: $18.50
     - Error rate: 0.5% ✓ EXCELLENT
     - Efficiency: 92/100 ⭐
     
     Groq performance:
     - Avg latency: 0.8 seconds ⭐ FASTEST
     - Total tokens: 500K
     - Total cost: $0.12
     - Error rate: 1.2%
     - Efficiency: 95/100 ⭐
     
     Recommendation: Use Groq for speed-critical queries"

monitor_rag_effectiveness(company_id, days=7) → RAGReport:
  Input: company_id, lookback period
  Process:
    1. Query all RAG retrieval operations
    2. Calculate metrics:
       - Avg documents retrieved
       - Avg retrieval time
       - Hit rate (found data)
       - Empty result rate
    3. Identify ineffective searches:
       - Searches returning no results
       - Searches taking > 2 seconds
    4. Return report
  Returns: {
    total_searches: int,
    avg_docs_retrieved: Decimal,
    avg_retrieval_time_ms: int,
    hit_rate: Decimal(5, 2),
    empty_result_rate: Decimal(5, 2),
    slow_searches: [...],
    no_result_searches: [...],
    recommendation: string
  }
  Example:
    "RAG Effectiveness Report
     - Total searches: 1,247
     - Avg documents retrieved: 8.3
     - Avg retrieval time: 1.2 seconds ✓
     - Hit rate: 94% ✓ EXCELLENT
     - Empty result rate: 6%
     
     Issues found:
     - 74 searches returned no results
       Most common: vendor name searches
       Recommendation: Index vendor names
     
     Slow searches:
     - GL account searches: 2.3 seconds
       Recommendation: Create index on account_code"

### 4. Service: AnomalyDetectionService

Purpose: Find unusual patterns and anomalies

detect_spending_anomalies(company_id, threshold_percentile=95) → AnomalyReport:
  Input: company_id, threshold (default 95th percentile)
  Process:
    1. Calculate normal spending distribution
    2. For each vendor:
       - Get historical spending
       - Calculate mean, std dev
       - Find outliers > threshold
    3. Identify unusual patterns:
       - Spending spike
       - Spending drop
       - New vendor
       - Unusual frequency
    4. Return anomalies
  Returns: {
    anomalies: [
      {
        vendor,
        amount,
        expected_range,
        status: SPIKE | DROP | NEW | UNUSUAL,
        severity: LOW | MEDIUM | HIGH,
        details
      }
    ],
    total_anomalies: int
  }
  Example Anomaly:
    "Anomaly Detected: ACME Corp
     - Normal monthly spending: €3,000-5,000
     - January spending: €45,000 (9x normal)
     - Status: SPENDING SPIKE
     - Severity: HIGH
     - Recommendation: Verify invoice for errors"

detect_revenue_anomalies(company_id, threshold_percentile=95) → RevenueAnomalyReport:
  Input: company_id, threshold
  Process:
    1. Calculate normal revenue distribution
    2. For each customer:
       - Get historical revenue
       - Calculate mean, std dev
       - Find outliers
    3. Identify patterns:
       - Revenue spike
       - Revenue drop
       - No activity
    4. Return anomalies
  Returns: {
    anomalies: [
      {
        customer,
        amount,
        expected_range,
        status: SPIKE | DROP | INACTIVE,
        days_inactive: int,
        severity: LOW | MEDIUM | HIGH
      }
    ]
  }

detect_reconciliation_anomalies(company_id) → ReconciliationAnomalyReport:
  Input: company_id
  Process:
    1. Find variances > €100
    2. Find old unmatched items (> 90 days)
    3. Find suspicious matches (confidence < 75%)
    4. Find patterns in variances
    5. Return anomalies
  Returns: {
    high_value_variances: [...],
    old_unmatched: [...],
    low_confidence_matches: [...],
    patterns: [...]
  }

detect_performance_anomalies(company_id) → PerformanceAnomalyReport:
  Input: company_id
  Process:
    1. Track query execution times
    2. Detect degradation:
       - Queries slower than 7-day avg
       - Error rate spike
       - Token usage spike
    3. Return anomalies
  Returns: {
    slow_query_spikes: [...],
    error_rate_spikes: [...],
    cost_spikes: [...],
    recommendation: string
  }

### 5. Service: DebuggingService

Purpose: Investigate and fix issues

debug_unmatched_invoice(company_id, invoice_id) → DebugReport:
  Input: company_id, invoice_id (specific invoice to debug)
  Process:
    1. Load invoice details:
       - Amount, vendor, date, reference
    2. Search for matching transactions:
       - Exact amount
       - Fuzzy amount (±1%, ±5%, ±10%)
       - Same date
       - Date ±5 days
       - Vendor match
    3. Analyze why no match found:
       - Amount doesn't exist in transactions
       - Vendor name different (typo)
       - Date mismatch
       - Payment method different
    4. Suggest fixes:
       - Corrective action needed
       - Data update needed
       - Manual match required
    5. Return debug report
  Returns: {
    invoice_details: {...},
    potential_matches_found: int,
    close_matches: [
      {transaction, similarity_score, reason_no_match}
    ],
    root_cause: string,
    suggested_actions: [...]
  }
  Example:
    "Debug: Invoice INV-001
     Amount: €5,000
     Vendor: ACME Corp
     Date: Jan 15
     Status: UNMATCHED
     
     Analysis:
     - No exact match found
     - Found 3 transactions from ACME in Jan:
       1. Jan 15: €5,000 ✓ Exact match!
          Reason no match: Vendor name 'ACME Corp' vs 'ACME'
       2. Jan 10: €3,000 (amount mismatch)
       3. Jan 20: €2,000 (date mismatch)
     
     Root Cause: Vendor name standardization issue
     
     Recommended Actions:
     1. Standardize vendor names (ACME vs ACME Corp)
     2. Run auto-match with fuzzy matching
     3. Manual match: INV-001 ↔ TXN-5000
     
     Resolution: Auto-matched ✅"

debug_gl_imbalance(company_id) → DebugReport:
  Input: company_id
  Process:
    1. Identify which accounts are unbalanced
    2. For each unbalanced account:
       - Find the last posting that was balanced
       - Search for errors since then
       - Calculate variance
       - Identify likely cause:
         * Duplicate posting
         * Wrong amount posted
         * Missing offset
         * Incorrect GL code
    3. Suggest corrections
    4. Return debug report
  Returns: {
    unbalanced_amount: Decimal,
    affected_accounts: [...],
    suspected_causes: [
      {posting_id, account, amount, reason_suspect, confidence}
    ],
    suggested_corrections: [
      {action, posting_id, account}
    ]
  }
  Example:
    "Debug: GL Out of Balance
     Total variance: €500
     
     Affected account: 5010 Expense Account
     Imbalance: €500 debit excess
     
     Analysis of recent postings:
     - Jan 29: JE-100 (€5,000 debit, €5,000 credit) ✓ OK
     - Jan 28: JE-99 (€500 debit, €0 credit) ❌ UNBALANCED!
     
     Root Cause: Journal Entry JE-99
     - Posted debit to 5010: €500
     - Missing credit posting
     
     Recommended Actions:
     1. Reverse JE-99
     2. Create corrected JE with matching credit
     3. Repost both entries
     
     Or:
     1. Add missing credit posting to offset €500"

debug_slow_query(company_id, query_type) → QueryDebugReport:
  Input: company_id, query_type (e.g., "invoice_search")
  Process:
    1. Profile the query:
       - Analyze execution plan
       - Check for missing indices
       - Check for full table scans
       - Check for N+1 problems
    2. Measure performance:
       - Baseline (good state)
       - Current (slow state)
    3. Identify bottleneck:
       - Missing index on vendor_id?
       - Full table scan?
       - Too much data retrieved?
    4. Suggest optimization
    5. Return debug report
  Returns: {
    query: string,
    current_execution_time: int,
    baseline_execution_time: int,
    slowdown_factor: Decimal,
    bottlenecks: [
      {type, details, impact}
    ],
    suggested_optimization: string,
    estimated_improvement: int
  }
  Example:
    "Debug: Slow Invoice Search
     Current time: 3.2 seconds
     Baseline (historical): 0.8 seconds
     Slowdown: 4x slower
     
     Bottleneck identified:
     - Full table scan on invoices (50K rows)
     - Scanning columns: vendor_id, amount, date
     - No index on vendor_id
     
     Suggested optimization:
     CREATE INDEX idx_invoices_vendor
     ON invoices(vendor_id, date);
     
     Estimated improvement: 50x faster
     New execution time: 64ms"

debug_high_cost(company_id, provider, threshold_date) → CostDebugReport:
  Input: company_id, provider, date where cost spiked
  Process:
    1. Analyze costs before/after date
    2. Identify what changed:
       - More conversations?
       - Longer conversations?
       - More tokens per request?
    3. Find root cause:
       - Larger context windows?
       - More RAG documents?
       - More LLM calls?
    4. Suggest optimization
    5. Return debug report
  Returns: {
    cost_before: Decimal,
    cost_after: Decimal,
    cost_increase: Decimal,
    increase_percentage: Decimal(5, 2),
    cause_analysis: [
      {factor, contribution_percentage}
    ],
    suggested_optimizations: [...]
  }
  Example:
    "Debug: High Claude Cost Spike
     Cost Jan 1-28: $12.50
     Cost Jan 29: $8.75 (daily average: $2.18/day)
     Spike: $6.25 increase in 1 day
     
     Cause analysis:
     - Token usage per request: +45%
     - Request count: +10%
     - Context size: +60% (more history included)
     
     Root cause: Context window set too large
     Retrieving 100+ messages instead of 20
     
     Recommended optimizations:
     1. Reduce context_window_messages: 100 → 20
     2. Summarize old messages instead of including full text
     3. Use Groq for cost-sensitive queries
     
     Expected savings: 80% reduction (€2 → €0.40/day)"

### 6. Service: RecommendationService

Purpose: Provide actionable recommendations

get_system_recommendations(company_id, category=None) → RecommendationList:
  Input: company_id, category (optional: performance, data, cost, reconciliation)
  Process:
    1. Run diagnostics
    2. Compile all recommendations from checks
    3. Prioritize by impact:
       - Critical fixes first
       - Performance improvements second
       - Data quality third
       - Cost optimization fourth
    4. Return prioritized list
  Returns: {
    recommendations: [
      {
        priority: CRITICAL | HIGH | MEDIUM | LOW,
        category: string,
        issue: string,
        current_state: string,
        recommended_action: string,
        estimated_impact: string,
        effort: EASY | MEDIUM | HARD,
        estimated_time: string
      }
    ]
  }
  Example Recommendation List:
    "SYSTEM RECOMMENDATIONS (Prioritized)
     
     🔴 CRITICAL (Fix immediately):
     1. GL Out of Balance by €500
        Effort: EASY (5 min)
        Action: Reverse JE-99, create corrected entry
        Impact: Fix GL integrity
     
     🟠 HIGH (Fix this week):
     1. Create index on invoices.vendor_id
        Effort: EASY (1 min)
        Action: Run SQL command
        Impact: 50x faster vendor searches
     
     2. 12 unmatched invoices (€5,000)
        Effort: MEDIUM (30 min)
        Action: Run invoice reconciliation
        Impact: Clear outstanding items
     
     🟡 MEDIUM (Fix this month):
     1. Standardize vendor names
        Effort: HARD (2 hours)
        Action: Audit and update 50 vendor records
        Impact: Better matching accuracy
     
     🟢 LOW (Optimize over time):
     1. Use Groq for speed-critical queries
        Effort: EASY (5 min)
        Action: Update LLM provider config
        Impact: 50% faster response, 98% cheaper"

### 7. Testing Requirements (80%+ MINIMUM)

Diagnostic Tests:
  [ ] GL balance check passes (balanced GL)
  [ ] GL balance check fails (detects imbalance)
  [ ] Invoice reconciliation check works
  [ ] Transaction matching check works
  [ ] Data completeness detection works
  [ ] Duplicate detection finds duplicates
  [ ] Performance monitoring accurate
  [ ] LLM performance tracking works
  [ ] RAG effectiveness measured
  [ ] Anomaly detection finds spending spikes
  [ ] Revenue anomaly detection works
  [ ] Reconciliation anomaly detection works
  [ ] Debug unmatched invoice works
  [ ] Debug GL imbalance works
  [ ] Debug slow queries works
  [ ] Debug high costs works
  [ ] Recommendations generated

AI Agent Integration:
  [ ] User asks "Is my system healthy?" → runs diagnostic
  [ ] User asks "Why is this query slow?" → debug report
  [ ] User asks "Why isn't this matched?" → debug unmatched
  [ ] User asks "How's my spending?" → anomaly detection
  [ ] User asks "What should I fix?" → recommendations
  [ ] Diagnostics run automatically nightly
  [ ] Alerts sent for critical issues

## Code Structure

jarvis/ai_agent/diagnostics/
├── services/
│   ├── system_health_service.py        (600+ lines)
│   ├── data_integrity_service.py       (600+ lines)
│   ├── performance_monitoring_service.py (500+ lines)
│   ├── anomaly_detection_service.py    (400+ lines)
│   ├── debugging_service.py            (500+ lines)
│   ├── recommendation_service.py       (300+ lines)
│   └── diagnostic_orchestrator.py      (300+ lines)
├── models.py                            (300+ lines)
├── repositories.py                      (200+ lines)
└── tests/
    ├── test_system_health.py           (400+ lines)
    ├── test_data_integrity.py          (400+ lines)
    ├── test_performance_monitoring.py  (300+ lines)
    ├── test_anomaly_detection.py       (300+ lines)
    ├── test_debugging.py               (400+ lines)
    ├── test_recommendations.py         (300+ lines)
    └── test_integration.py             (500+ lines)

## Database Schema

CREATE TABLE diagnostic_results (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL REFERENCES companies(id),
    diagnostic_type VARCHAR(100) NOT NULL,
    status VARCHAR(50) NOT NULL,
    score INTEGER (0-100),
    details JSONB,
    created_at TIMESTAMP NOT NULL
);

CREATE TABLE detected_anomalies (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL REFERENCES companies(id),
    anomaly_type VARCHAR(100),
    severity VARCHAR(50),
    description TEXT,
    data JSONB,
    resolution_status VARCHAR(50),
    created_at TIMESTAMP NOT NULL,
    resolved_at TIMESTAMP
);

CREATE TABLE system_recommendations (
    id UUID PRIMARY KEY,
    company_id UUID NOT NULL REFERENCES companies(id),
    priority VARCHAR(50),
    category VARCHAR(100),
    issue TEXT,
    action_recommended TEXT,
    estimated_impact TEXT,
    effort_required VARCHAR(50),
    implemented BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP NOT NULL
);

## Scheduled Diagnostics

Nightly (2 AM UTC):
  - Run full system diagnostic
  - Detect anomalies
  - Generate recommendations
  - Send alert if critical issues found

Weekly (Monday 6 AM UTC):
  - Performance analysis report
  - Anomaly trend analysis
  - Cost efficiency review

Monthly (1st of month, 9 AM UTC):
  - Comprehensive health report
  - Data quality assessment
  - Optimization opportunities

## AI Agent Chat Integration

Users can now ask diagnostic questions:

```
User: "Is my system healthy?"
AI: "Your system health score is 72/100 ⚠️
    - GL is balanced ✓
    - 12 invoices unmatched ⚠️
    - Performance degraded 🔴
    [Full report attached]"

User: "Debug why JE-99 is causing GL imbalance"
AI: "JE-99 has €500 debit with no matching credit.
    This is causing the GL imbalance.
    Suggested fix: Add €500 credit to offset."

User: "What should I fix this week?"
AI: "Top 3 recommendations:
    1. Create index on vendor_id (5 min, 50x speedup)
    2. Reconcile 12 unmatched invoices (30 min)
    3. Fix GL imbalance from JE-99 (5 min)"

User: "Why is spending with ACME so high?"
AI: "Anomaly detected: ACME spending €45,000 (9x normal)
    Normal range: €3,000-5,000
    This is a 900% spike - verify invoice for errors."
```

## Golden Rules for Diagnostics

1. ✅ **PROACTIVE** - Find problems before they cause issues
2. ✅ **TRANSPARENT** - Show exactly what's wrong and why
3. ✅ **ACTIONABLE** - Provide specific steps to fix
4. ✅ **AUTOMATED** - Run nightly, alert on critical
5. ✅ **ACCURATE** - Data-backed analysis, no guesses
6. ✅ **PRIORITIZED** - Critical first, nice-to-have last
7. ✅ **MEASURABLE** - Show impact of each recommendation
8. ✅ **AUDITABLE** - All diagnostics logged for compliance

## Success Criteria

Code is DONE when:

✅ System health score calculated
✅ All 10 checks implemented
✅ GL balance verified
✅ Invoice reconciliation checked
✅ Data completeness measured
✅ Duplicates detected
✅ Performance bottlenecks identified
✅ Missing indices found
✅ Slow queries identified
✅ Anomalies detected (spending, revenue, reconciliation)
✅ Unmatched items debugged
✅ GL imbalance debugged
✅ Slow queries debugged
✅ High costs debugged
✅ Recommendations prioritized
✅ Scheduled diagnostics work
✅ Alerts sent on critical
✅ 80%+ test coverage
✅ AI can answer diagnostic questions
✅ Ready for production
✅ Ready to merge

================================================================================
END OF DIAGNOSTICS SPECIFICATION
================================================================================
