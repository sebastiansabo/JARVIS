# JARVIS AI Agent + Diagnostics - Complete Integration Guide

**Status**: Ready for implementation  
**Created**: 2026-01-29  
**Total Code**: ~15,000 lines (AI Agent + Diagnostics)  

## What You Have

### 4 Complete Specification Documents

1. **AI_AGENT_CLAUDE_CODE_PROMPT.txt** (8,500+ lines)
   - Main AI Agent service (RAG, LLM, conversations)
   - Multi-provider LLM support (Claude, ChatGPT, Gemini, Groq)
   - 70%+ test coverage
   - ~6,000 lines generated code

2. **AI_AGENT_DIAGNOSTICS_CLAUDE_CODE_PROMPT.txt** (5,000+ lines)
   - System diagnostics and health checks
   - Anomaly detection (spending, revenue, reconciliation, performance)
   - Debugging services (GL imbalance, slow queries, high costs)
   - Recommendations engine
   - 80%+ test coverage
   - ~3,500 lines generated code

3. **AI_AGENT_MODULE_SPECIFICATION.md** (500+ lines)
   - Architecture overview
   - Feature descriptions
   - Example conversations
   - Cost models

4. **AI_AGENT_DIAGNOSTICS_SPECIFICATION.md** (400+ lines)
   - Diagnostics architecture
   - Service specifications
   - Example diagnostic reports

## Architecture

```
┌────────────────────────────────────────────────────────────┐
│                    USER INTERFACE                          │
│  (Web chat, API, voice assistant)                         │
└────────────────┬───────────────────────────────────────────┘
                 │
         Chat message or diagnostic query
                 │
    ┌────────────▼─────────────┐
    │  AI AGENT SERVICE        │
    │  (Main orchestration)    │
    ├──────────────────────────┤
    │ - Chat handling          │
    │ - RAG pipeline           │
    │ - LLM provider routing   │
    │ - Conversation mgmt      │
    └────────────┬──────────────┘
                 │
     ┌───────────┴───────────┬──────────────────┐
     │                       │                  │
     ↓                       ↓                  ↓
┌──────────────┐    ┌─────────────────┐  ┌────────────────┐
│ RAG Pipeline │    │ LLM Providers   │  │ DIAGNOSTICS    │
│              │    │                 │  │ SERVICE        │
│ - Retrieve   │    │ • Claude        │  │                │
│   JARVIS     │    │ • ChatGPT       │  │ • Health check │
│   data       │    │ • Gemini        │  │ • Data integ.  │
│ - Semantic   │    │ • Groq          │  │ • Performance  │
│   search     │    │                 │  │ • Anomalies    │
│ - Citations  │    │ (Auto-fallback) │  │ • Debugging    │
└──────────────┘    └─────────────────┘  │ • Recommend.   │
                                         └────────────────┘
     │                    │
     └────────┬───────────┘
              │
    ┌─────────▼──────────────┐
    │ JARVIS DATA ACCESS     │
    │ (Read-only)            │
    ├────────────────────────┤
    │ GL, Invoices,          │
    │ Transactions,          │
    │ Reports, etc.          │
    └────────────────────────┘
```

## Two-Phase Implementation

### Phase 1: AI Agent (6,000 lines)
- User asks questions
- AI retrieves JARVIS data
- AI responds with answers
- Tracks costs across providers

### Phase 2: Diagnostics (3,500 lines)
- System monitors itself
- Identifies weaknesses
- Suggests improvements
- Debugs issues automatically

## Example Workflows

### Workflow 1: Simple Question (AI Agent Only)

```
User: "What's my current cash balance?"

1. AI Agent processes message
2. RAG retrieves GL Bank Account (1010)
3. Claude API called for response
4. Response: "€50,432.15 [from GL posting]"

Flow:
  Message → AIAgentService.chat()
         → RAGPipelineService.retrieve_gl_data()
         → LLMProviderService.send_to_claude()
         → Response
```

### Workflow 2: Diagnostic Question (AI Agent + Diagnostics)

```
User: "Is my system healthy?"

1. AI Agent detects diagnostic intent
2. Calls SystemHealthService.run_full_diagnostic()
3. Returns health report (score: 72/100)
4. AI formats report for user
5. Response: "Your system health score is 72/100 ⚠️
    - GL balanced ✓
    - 12 invoices unmatched ⚠️
    - Performance issues 🔴
    [Full diagnostic report]"

Flow:
  Message → AIAgentService.chat()
         → Intent detection: "diagnostic"
         → SystemHealthService.run_full_diagnostic()
         → DiagnosticOrchestrator.compile_results()
         → Response formatter
         → Response
```

### Workflow 3: Debugging (AI Agent + Diagnostics)

```
User: "Why isn't invoice INV-001 matching?"

1. AI Agent detects debug intent
2. Calls DebuggingService.debug_unmatched_invoice("INV-001")
3. Returns debug analysis:
   - Vendor name mismatch (ACME vs ACME Corp)
   - Amount match found (€5,000)
   - Date match found (Jan 15)
4. AI suggests fix and next steps
5. Response: "Invoice INV-001 has a vendor name mismatch...
    Suggested fix: Standardize vendor names"

Flow:
  Message → AIAgentService.chat()
         → Intent detection: "debug"
         → DebuggingService.debug_unmatched_invoice()
         → Response with analysis
```

### Workflow 4: Automated Nightly Diagnostic

```
Scheduled: 2 AM UTC every night

1. DiagnosticOrchestrator.run_full_system_diagnostic()
2. Checks:
   ✓ GL balance
   ✓ Invoice reconciliation
   ✓ Data completeness
   ✓ Performance metrics
   ✓ Anomalies
3. Generates health report
4. If critical issues:
   → Send alert email to finance manager
   → Log to diagnostic_results table
5. Store recommendations
6. Next time user asks "What should I fix?"
   → AI provides latest recommendations
```

## File Structure After Generation

```
jarvis/
├── ai_agent/
│   ├── services/
│   │   ├── ai_agent_service.py           (main orchestration)
│   │   ├── rag_pipeline_service.py
│   │   ├── llm_provider_service.py
│   │   ├── conversation_service.py
│   │   └── ... (7 total services)
│   ├── providers/
│   │   ├── claude_provider.py
│   │   ├── chatgpt_provider.py
│   │   ├── gemini_provider.py
│   │   └── groq_provider.py
│   ├── models.py
│   ├── repositories.py
│   └── tests/
│       ├── test_ai_agent_service.py
│       ├── test_rag_pipeline.py
│       ├── test_llm_providers.py
│       └── ... (8 total test files)
│
└── ai_agent/diagnostics/
    ├── services/
    │   ├── system_health_service.py      (health checks)
    │   ├── data_integrity_service.py
    │   ├── performance_monitoring_service.py
    │   ├── anomaly_detection_service.py
    │   ├── debugging_service.py
    │   ├── recommendation_service.py
    │   └── diagnostic_orchestrator.py
    ├── models.py
    ├── repositories.py
    └── tests/
        ├── test_system_health.py
        ├── test_data_integrity.py
        ├── test_anomaly_detection.py
        ├── test_debugging.py
        └── ... (7 total test files)
```

## Implementation Timeline

### Day 1: Setup (30 min)

```bash
# 1. Get API keys (10 min)
# Create .env with:
# - CLAUDE_API_KEY
# - OPENAI_API_KEY
# - GROQ_API_KEY

# 2. Update config (10 min)
# Edit .claude-code/config.json with provider settings

# 3. Prepare Claude Code (10 min)
# Load JARVIS system prompt
```

### Day 1: Generate AI Agent (10 min)

```bash
# Paste AI_AGENT_CLAUDE_CODE_PROMPT.txt into Claude Code
# Wait for generation (~5 min)
# Review output (5 min)
# Approve
```

### Day 1: Test AI Agent (30 min)

```bash
# Run tests
pytest jarvis/ai_agent/tests/ -v --cov

# Expected: 70%+ coverage, all tests pass
# Estimated time: 30 sec to run, 30 min to review
```

### Day 1: Deploy AI Agent (30 min)

```bash
# Create database tables
python jarvis/ai_agent/migrations.py

# Test basic functionality
python -c "
from jarvis.ai_agent.services import AIAgentService
session = AIAgentService.initialize_chat_session('company-uuid', 'test-user')
response = AIAgentService.chat(session.id, 'What is 1+1?')
print(response.response_text)
"

# Commit code
git add jarvis/ai_agent/
git commit -m 'feat: Add AI Agent module with RAG and multi-provider LLM support'
```

### Day 2: Generate Diagnostics (10 min)

```bash
# Paste AI_AGENT_DIAGNOSTICS_CLAUDE_CODE_PROMPT.txt into Claude Code
# Wait for generation (~5 min)
# Review output (5 min)
# Approve
```

### Day 2: Test Diagnostics (30 min)

```bash
# Run tests
pytest jarvis/ai_agent/diagnostics/tests/ -v --cov

# Expected: 80%+ coverage, all tests pass
```

### Day 2: Deploy Diagnostics (30 min)

```bash
# Create tables
python jarvis/ai_agent/diagnostics/migrations.py

# Schedule nightly diagnostic
python -c "
from jarvis.ai_agent.diagnostics import DiagnosticOrchestrator
DiagnosticOrchestrator.schedule_nightly_diagnostic('company-uuid')
"

# Commit code
git add jarvis/ai_agent/diagnostics/
git commit -m 'feat: Add diagnostics and debugging for AI Agent'
```

### Day 2-3: Integration & Polish (2-4 hours)

```bash
# Test multi-provider switching
# Test conversation context across sessions
# Test diagnostic alerts
# Test RAG with different query types
# Performance testing
# Documentation
```

**Total Time: ~2 days**

## Quick Start Checklist

### Before Generation

- [ ] Copy API keys to .env
  - [ ] CLAUDE_API_KEY (from https://console.anthropic.com/)
  - [ ] OPENAI_API_KEY (from https://platform.openai.com/)
  - [ ] GROQ_API_KEY (from https://console.groq.com/)

- [ ] Update .claude-code/config.json
  - [ ] Add llm_providers section
  - [ ] Add ai_agent section
  - [ ] Set default provider (recommend: claude)

- [ ] Open Claude Code
  - [ ] Load JARVIS system prompt

### Phase 1: AI Agent

- [ ] Paste AI_AGENT_CLAUDE_CODE_PROMPT.txt
- [ ] Generate code (~5 min)
- [ ] Review (30 min)
- [ ] Approve
- [ ] Run tests: `pytest jarvis/ai_agent/tests/ -v --cov`
- [ ] Expected: 70%+ coverage
- [ ] Create database: `python jarvis/ai_agent/migrations.py`
- [ ] Quick test:
  ```python
  from jarvis.ai_agent.services import AIAgentService
  response = AIAgentService.chat(session_id, "What is my cash balance?")
  ```
- [ ] Commit: `git commit -m "feat: Add AI Agent module"`

### Phase 2: Diagnostics

- [ ] Paste AI_AGENT_DIAGNOSTICS_CLAUDE_CODE_PROMPT.txt
- [ ] Generate code (~5 min)
- [ ] Review (30 min)
- [ ] Approve
- [ ] Run tests: `pytest jarvis/ai_agent/diagnostics/tests/ -v --cov`
- [ ] Expected: 80%+ coverage
- [ ] Create database: `python jarvis/ai_agent/diagnostics/migrations.py`
- [ ] Test:
  ```python
  from jarvis.ai_agent.diagnostics import SystemHealthService
  report = SystemHealthService.run_full_diagnostic(company_id)
  ```
- [ ] Commit: `git commit -m "feat: Add diagnostics and debugging"`

### Post-Deployment

- [ ] Configure email alerts for critical issues
- [ ] Set up monitoring dashboard
- [ ] Schedule nightly diagnostics
- [ ] Document supported queries for team
- [ ] Train users on system

## Cost Projections

| Provider | Cost/1K input | Cost/1K output | Use Case |
|----------|---------------|----------------|----------|
| Claude | $0.003 | $0.015 | Smart analysis (default) |
| ChatGPT | $0.010 | $0.030 | General use |
| Gemini | $0.0005 | $0.0015 | Budget option |
| Groq | $0.00024 | $0.00024 | Speed-critical, ultra-cheap |

**Sample Monthly Costs (100 users, 10 conversations each, 10 messages per)**

```
100 users × 10 conversations × 10 messages = 10,000 messages/month

Per message (average):
  Input: 200 tokens
  Output: 100 tokens

Claude option:
  Input cost: 10K × 200/1000 × $0.003 = $6.00
  Output cost: 10K × 100/1000 × $0.015 = $15.00
  Total: $21.00/month = $0.21 per user

Groq option (ultra-cheap):
  Input cost: 10K × 200/1000 × $0.00024 = $0.48
  Output cost: 10K × 100/1000 × $0.00024 = $0.24
  Total: $0.72/month = $0.007 per user

Time savings value:
  1 hour lookup reduced to 1 minute = 59 minutes saved
  100 users × 59 min × €0.5/min = €2,950 value/month

ROI: (€2,950 - €0.72) / €0.72 = **4,097x return**
```

## Diagnostic Examples

### Health Check Report

```
SYSTEM HEALTH REPORT
═══════════════════════════════════════════════════════════
Overall Health Score: 72/100 ⚠️  NEEDS ATTENTION
Generated: 2026-01-29 02:00 UTC

CHECK RESULTS:
─────────────────────────────────────────────────────────

✅ PASS: GL Balance Check (100/100)
   Status: All accounts balanced
   Details: Total debits = €1,234,567.89 = Total credits

⚠️  WARNING: Invoice Reconciliation (60/100)
   Status: Some unmatched invoices
   Details: 12 invoices unmatched totaling €5,000
   Age: Some unmatched for 45+ days
   Action: Run reconciliation process

❌ CRITICAL: Performance Degradation (40/100)
   Status: Database performance declining
   Details: Average query time: 3.2 seconds (target: 1s)
   Cause: Missing indices on frequently-queried columns
   Action: Create indices on vendor_id, customer_id, date

⚠️  WARNING: Data Quality (65/100)
   Status: Some incomplete records
   Details: 18 records missing critical fields
   Examples: 3 invoices missing vendor_id, 15 transactions with UNKNOWN description
   Action: Data cleansing needed

⚠️  WARNING: Cost Efficiency (70/100)
   Status: LLM costs slightly elevated
   Details: Average 250 tokens per message (typically 150)
   Cause: Longer context window included
   Action: Reduce max context messages from 100 to 20

WEAK POINTS:
─────────────────────────────────────────────────────────
1. Invoice reconciliation not run in 5 days
2. Missing database indices (blocking performance)
3. 18 incomplete/incorrect records
4. Context window too large (increasing costs)

TOP 5 RECOMMENDATIONS (Prioritized):
─────────────────────────────────────────────────────────
🔴 CRITICAL:
   1. Create database indices (5 min)
      → Improves query speed: 50x
      → Impact: Diagnostics complete in 64ms instead of 3.2 seconds

🟠 HIGH:
   1. Run invoice reconciliation (30 min)
      → Clears 12 unmatched items
      → Impact: Perfect reconciliation

   2. Reduce context window (2 min)
      → Reduces costs: 40% savings
      → Impact: €8.40/month savings

🟡 MEDIUM:
   1. Clean up 18 incomplete records (1 hour)
      → Improves data quality: 95% → 99%
      → Impact: Better matching accuracy

Next check: Tomorrow 2 AM UTC
```

### Anomaly Report

```
ANOMALY DETECTION REPORT
═══════════════════════════════════════════════════════════

SPENDING ANOMALIES:
─────────────────────────────────────────────────────────

🔴 HIGH SEVERITY: ACME Corp
   Normal monthly spending: €3,000 - €5,000
   January spending: €45,000
   Spike: 9x normal (900% increase)
   Confidence: 99%
   
   Recommendation: Verify invoice amounts
   Action: Review invoice INV-001 (€45,000)

🟠 MEDIUM SEVERITY: Office Supplies Inc
   Normal monthly spending: €1,500 - €2,000
   January spending: €4,500
   Spike: 2.2x normal (120% increase)
   Confidence: 87%
   
   Recommendation: Confirm legitimacy
   Action: Check for duplicate entries

REVENUE ANOMALIES:
─────────────────────────────────────────────────────────

✓ No unusual revenue patterns

RECONCILIATION ANOMALIES:
─────────────────────────────────────────────────────────

⚠️  €5,000 variance in January reconciliation
   Age: 14 days unresolved
   Impact: GL and bank balance don't match by €5K
   
   Recommendation: Investigate and resolve
   Action: Run variance investigation

Summary: 2 spending anomalies, 1 reconciliation anomaly
```

### Debug Report Example

```
DEBUG: Why is Invoice INV-001 not matching?
═══════════════════════════════════════════════════════════

INVOICE DETAILS:
─────────────────────────────────────────────────────────
ID: INV-001
Vendor: ACME Corp
Amount: €5,000
Date: Jan 15, 2026
Status: UNMATCHED (0 matching transactions)

ANALYSIS:
─────────────────────────────────────────────────────────

Search Results:
1. Transaction TXN-5000
   Amount: €5,000 ✓ EXACT MATCH
   Vendor: ACME (vs "ACME Corp") ⚠️ NAME MISMATCH
   Date: Jan 15 ✓ EXACT MATCH
   Match Score: 95/100
   
   Why not matched: Vendor name standardization issue
   - Invoice: "ACME Corp"
   - Transaction: "ACME"
   - System: Uses fuzzy matching but threshold set too high

2. Transaction TXN-3000
   Amount: €3,000 (vs €5,000) ❌ AMOUNT MISMATCH
   Date: Jan 10 (vs Jan 15) ❌ DATE MISMATCH

3. Transaction TXN-2000
   Amount: €2,000 (vs €5,000) ❌ AMOUNT MISMATCH
   Date: Jan 20 (vs Jan 15) ❌ DATE MISMATCH

ROOT CAUSE:
─────────────────────────────────────────────────────────
Vendor name not standardized. Invoice has "ACME Corp" but transaction has "ACME".
Match algorithm found transaction but fuzzy-match threshold blocked it.

RECOMMENDED ACTIONS (in order):
─────────────────────────────────────────────────────────
1. IMMEDIATE: Manual match INV-001 ↔ TXN-5000
   Time: 2 minutes
   
2. SHORT-TERM: Standardize vendor names
   Action: Rename "ACME" to "ACME Corp" in all transactions
   Time: 30 minutes
   Impact: Prevents future mismatches
   
3. LONG-TERM: Adjust fuzzy-match threshold
   Action: Lower threshold from 95 to 85 for high-match items
   Time: 5 minutes
   Impact: Auto-match similar vendors

Resolution:
✓ Manual matched: INV-001 → TXN-5000
```

## Support & Troubleshooting

### Common Issues

**Issue: "API key invalid"**
```
Solution:
1. Verify API key in .env
2. Check key hasn't been revoked
3. Regenerate key from provider console
4. Update .env and redeploy
```

**Issue: "Slow queries after deployment"**
```
Solution:
1. Run SystemHealthService.check_performance()
2. Look for missing indices
3. Create recommended indices
4. Test performance again
```

**Issue: "High costs"**
```
Solution:
1. Run DebuggingService.debug_high_cost()
2. Identify root cause (more requests? longer context?)
3. Implement suggested optimization
4. Monitor costs next week
```

**Issue: "Unmatched invoices"**
```
Solution:
1. Run DebuggingService.debug_unmatched_invoice()
2. Identify root cause (vendor name, amount, date)
3. Implement suggested fix
4. Run reconciliation
```

## Next Steps

1. **Read the specifications** (30 min)
   - AI_AGENT_MODULE_SPECIFICATION.md
   - AI_AGENT_DIAGNOSTICS_SPECIFICATION.md

2. **Prepare environment** (30 min)
   - Get API keys from providers
   - Update .env and config.json

3. **Generate Phase 1** (30 min)
   - Paste AI_AGENT_CLAUDE_CODE_PROMPT.txt
   - Generate and review
   - Run tests

4. **Deploy Phase 1** (30 min)
   - Create database
   - Test functionality
   - Commit code

5. **Generate Phase 2** (30 min)
   - Paste AI_AGENT_DIAGNOSTICS_CLAUDE_CODE_PROMPT.txt
   - Generate and review
   - Run tests

6. **Deploy Phase 2** (30 min)
   - Create database
   - Schedule nightly diagnostics
   - Commit code

7. **Integrate & Polish** (2-4 hours)
   - Test multi-turn conversations
   - Test diagnostic questions
   - Test provider switching
   - Documentation
   - Team training

**Total Implementation Time: ~2-3 days**

---

## Files Reference

- **AI_AGENT_CLAUDE_CODE_PROMPT.txt** → Use to generate Phase 1 (AI Agent)
- **AI_AGENT_DIAGNOSTICS_CLAUDE_CODE_PROMPT.txt** → Use to generate Phase 2 (Diagnostics)
- **AI_AGENT_MODULE_SPECIFICATION.md** → Read for architecture details
- **AI_AGENT_DIAGNOSTICS_SPECIFICATION.md** → Read for diagnostics details
- **AI_AGENT_DEPLOYMENT_GUIDE.md** → Use for deployment steps

All files available in `/mnt/user-data/outputs/`

---

**Ready to build?** 🚀

Your JARVIS AI Agent is ready to serve your business. It will:
✅ Answer business questions
✅ Identify system weaknesses
✅ Detect performance issues
✅ Find data problems
✅ Suggest improvements
✅ Debug issues automatically

Let's go! 🎯
