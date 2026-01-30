# JARVIS AI Agent Module - Deployment Guide

**Status**: Ready for Claude Code generation  
**Created**: 2026-01-29  
**Version**: 1.0  

## What's Been Created

You now have two complete files for the AI Agent module:

1. **`AI_AGENT_CLAUDE_CODE_PROMPT.txt`** (8,500+ lines)
   - Complete Claude Code generation prompt
   - Ready to paste directly into Claude Code
   - Includes all requirements, specifications, tests

2. **`AI_AGENT_MODULE_SPECIFICATION.md`** (500+ lines)
   - Technical overview
   - Architecture diagrams
   - Use cases and examples
   - Configuration reference

## What the AI Agent Does

JARVIS AI Agent is a conversational chatbot that:

**Answers Questions About Your Business Data**
```
User: "What are my top vendors?"
AI: "Your top vendors in January 2026 are:
    1. ACME Corp - €45,000
    2. Office Supplies - €15,000
    3. Tech Services - €12,000
    [from Invoice data]"
```

**Supports Multiple AI Models**
- Claude (Anthropic) - smartest, good for analysis
- ChatGPT (OpenAI) - popular, balanced
- Gemini (Google) - free tier available
- Groq (High-speed) - cheapest, fastest

**Maintains Conversation Context**
```
User: "Am I profitable?"
AI: "Yes, net income €24,300"

User: "How does that compare to December?"
AI: "December was €21,900, so +11% improvement"
[remembers previous question]
```

**Uses RAG (Retrieval-Augmented Generation)**
- Retrieves relevant data from JARVIS first
- Grounds responses in your actual data
- Never hallucinate or make up information
- Cites data sources

## Quick Start

### Step 1: Copy API Keys to Environment

Create or update `.env` in your JARVIS root:

```bash
# Claude API (Anthropic)
CLAUDE_API_KEY=sk-ant-xxxxx

# OpenAI API (ChatGPT)
OPENAI_API_KEY=sk-xxxxx

# Google Gemini API
GOOGLE_API_KEY=xxxxx

# Groq API (optional, fastest/cheapest)
GROQ_API_KEY=gsk_xxxxx
```

Get API keys from:
- Claude: https://console.anthropic.com/
- OpenAI: https://platform.openai.com/api-keys
- Google: https://makersuite.google.com/app/apikey
- Groq: https://console.groq.com/

### Step 2: Configure LLM Providers

In `.claude-code/config.json`, add under `llm_providers`:

```json
{
  "llm_providers": {
    "default_provider": "claude",
    "fallback_order": ["claude", "groq", "chatgpt"],
    
    "claude": {
      "enabled": true,
      "api_key": "${CLAUDE_API_KEY}",
      "model_name": "claude-opus-4-5-20251101",
      "cost_per_1k_input_tokens": 0.003,
      "cost_per_1k_output_tokens": 0.015
    },
    
    "chatgpt": {
      "enabled": true,
      "api_key": "${OPENAI_API_KEY}",
      "model_name": "gpt-4-turbo",
      "cost_per_1k_input_tokens": 0.010,
      "cost_per_1k_output_tokens": 0.030
    },
    
    "groq": {
      "enabled": true,
      "api_key": "${GROQ_API_KEY}",
      "model_name": "llama-3.3-70b-versatile",
      "cost_per_1k_input_tokens": 0.00024,
      "cost_per_1k_output_tokens": 0.00024
    }
  }
}
```

### Step 3: Generate Code with Claude Code

```bash
# 1. Open Claude Code in your JARVIS directory
cd /path/to/jarvis
# Open in editor or IDE with Claude Code extension

# 2. Load system prompt
.claude-code/system_prompt.md

# 3. Paste the prompt
cat AI_AGENT_CLAUDE_CODE_PROMPT.txt
# (Copy-paste into Claude Code input)

# 4. Claude Code generates:
# - 10 services (2,000+ lines)
# - RAG pipeline (500+ lines)
# - LLM provider abstraction (400+ lines)
# - 8 test files (1,500+ lines)
# - Total: ~6,000 lines of production code

# 5. Review output
# - Check generated files in jarvis/ai_agent/
# - Review test coverage (should be 70%+)
# - Approve and commit
```

### Step 4: Run Tests

```bash
# Run all AI Agent tests
pytest jarvis/ai_agent/tests/ -v --cov=jarvis/ai_agent

# Should see:
# ✓ test_ai_agent_service.py (PASS)
# ✓ test_rag_pipeline.py (PASS)
# ✓ test_llm_providers.py (PASS)
# ✓ test_conversation_management.py (PASS)
# ✓ test_cost_tracking.py (PASS)
# Coverage: 70%+
```

### Step 5: Initialize Database

```bash
# Create tables
python jarvis/ai_agent/migrations.py

# Verify
SELECT COUNT(*) FROM conversation_sessions;  -- Should be 0
```

### Step 6: Test Integration

```python
from jarvis.ai_agent.services import AIAgentService

# Create a test session
session = AIAgentService.initialize_chat_session(
    company_id="your-company-uuid",
    user_id="test-user",
    title="Test conversation"
)

# Send a test message
response = AIAgentService.chat(
    session_id=session.id,
    user_message="What's my current bank balance?"
)

print(response.response_text)
# Expected: "Your current bank account balance is €XX,XXX..."
```

## Architecture Overview

```
User Chat Interface
        │
        ↓
┌──────────────────────────────────┐
│  AIAgentService (orchestration)  │
│  - initialize_chat_session()     │
│  - chat()                        │
│  - get_conversation_history()    │
└──────────────┬───────────────────┘
               │
    ┌──────────┼──────────┬──────────┐
    ↓          ↓          ↓          ↓
┌────────┐ ┌────────┐ ┌──────────┐ ┌──────────┐
│RAG     │ │Intent  │ │Response  │ │Cost      │
│Pipeline│ │Detect. │ │Validation│ │Tracking  │
└────────┘ └────────┘ └──────────┘ └──────────┘
    │
    ↓
┌──────────────────────────────────┐
│  JARVIS Data Access (read-only)  │
│  - GL posting queries            │
│  - Invoice queries               │
│  - Transaction queries           │
│  - Report queries                │
│  - Reconciliation data           │
└──────────┬───────────────────────┘
           │
           ↓
┌──────────────────────────────────┐
│  LLMProviderService              │
│  - send_to_claude()              │
│  - send_to_chatgpt()             │
│  - send_to_gemini()              │
│  - send_to_groq()                │
└──────────┬───────────────────────┘
           │
           ↓
        AI Response
```

## Deployment Checklist

Before deploying to production:

### Configuration
- [ ] Set `CLAUDE_API_KEY` in `.env`
- [ ] Set `OPENAI_API_KEY` in `.env` (optional)
- [ ] Set `GROQ_API_KEY` in `.env` (optional)
- [ ] Update `config.json` with LLM provider configs
- [ ] Set `default_provider` (recommend: "claude")
- [ ] Configure rate limits per provider
- [ ] Set cost thresholds for alerts

### Database
- [ ] Create conversation_sessions table
- [ ] Create message_history table
- [ ] Create rag_contexts table
- [ ] Create cost_tracking table
- [ ] Create indices for performance
- [ ] Run migrations: `python jarvis/ai_agent/migrations.py`
- [ ] Verify tables created: `SELECT * FROM information_schema.tables WHERE table_schema = 'public'`

### Testing
- [ ] Run full test suite: `pytest jarvis/ai_agent/tests/ -v`
- [ ] Achieve 70%+ coverage
- [ ] Test with each LLM provider
- [ ] Test fallback scenarios
- [ ] Test rate limiting
- [ ] Performance test (< 5s response time)

### Security
- [ ] API keys encrypted in database
- [ ] No API keys logged in debug output
- [ ] Permission checks enforced
- [ ] Audit logging enabled
- [ ] HTTPS only (if web interface)

### Monitoring
- [ ] Set up cost tracking dashboard
- [ ] Monitor token usage by provider
- [ ] Track conversation count/trends
- [ ] Alert on high costs (e.g., > $100/month)
- [ ] Monitor error rates
- [ ] Track response times

### Documentation
- [ ] Document API endpoints
- [ ] Document example queries
- [ ] Document supported intents
- [ ] Document troubleshooting guide
- [ ] Document cost model

## Cost Estimates

**Monthly costs for 100 users, 10 conversations each, 10 messages per conversation:**

```
Claude (most used):
  1000 conversations × 200 input tokens × $0.003/1K = $0.60
  1000 conversations × 100 output tokens × $0.015/1K = $1.50
  Monthly: ~$2.10 (very cheap!)

ChatGPT (if used):
  1000 conversations × 200 input tokens × $0.010/1K = $2.00
  1000 conversations × 100 output tokens × $0.030/1K = $3.00
  Monthly: ~$5.00

Groq (budget option):
  1000 conversations × 200 input tokens × $0.00024/1K = $0.24
  1000 conversations × 100 output tokens × $0.00024/1K = $0.24
  Monthly: ~$0.48 (very cheap!)

Total (all providers): ~$7.58/month
Per user: ~$0.076/month
Cost per conversation: ~$0.008
Cost per message: ~$0.004
```

**ROI Example:**
- Cost: $7.58/month (AI agent)
- Time saved: 2 hours/month per user (no manual data lookups)
- Valuation: €30/hour × 2 hours × 100 users = €6,000/month value
- **ROI: 790x return on investment**

## Example Queries

The AI Agent understands and answers:

### Financial Queries
- "What's my current cash balance?"
- "What was our revenue last month?"
- "Am I profitable?"
- "What's my debt-to-equity ratio?"
- "Show me income statement for January"

### Vendor & Customer Analysis
- "Who are my top 10 vendors?"
- "How much have I spent with ACME?"
- "Which customer brought the most revenue?"
- "What are my top vendors by spending?"
- "Show customer aging report"

### Invoice & Transaction Queries
- "How many invoices are overdue?"
- "What transactions happened on Jan 15?"
- "Show me all invoices from ACME"
- "What's my outstanding receivable?"
- "List unpaid invoices"

### Forecasting & Analysis
- "What will my cash be in 30 days?"
- "Project revenue for Q2"
- "Compare January to December"
- "What's my burn rate?"
- "Calculate cash flow"

### Tax & Compliance
- "How much VAT do I owe?"
- "What's my tax liability?"
- "Show tax report for January"
- "Calculate quarterly tax"

## Troubleshooting

### "Response took too long"
- **Cause**: LLM provider slow or network latency
- **Fix**: Use Groq (fastest) or check internet connection

### "No data found for your query"
- **Cause**: Query too ambiguous or no matching data
- **Fix**: Ask AI to suggest refined query

### "Permission denied"
- **Cause**: User doesn't have access to requested data
- **Fix**: Check ConversationPermission table

### "API key invalid"
- **Cause**: Wrong API key or expired key
- **Fix**: Regenerate key from provider console

### "Rate limit exceeded"
- **Cause**: Too many requests
- **Fix**: Wait a minute or upgrade plan

### "Response contains hallucination"
- **Cause**: AI made up data not in JARVIS
- **Fix**: This is detected and blocked automatically

## Integration with Other JARVIS Modules

AI Agent **reads from** (read-only):
- `accounting_core` - GL postings, accounts
- `invoicing` - Invoices (sent & received)
- `bank_import` - Transactions, bank accounts
- `reconciliation` - Matched items, variances
- `reporting` - Generated reports
- `vendors`, `customers` - Entity data

AI Agent **cannot modify** any of these (read-only by design).

## Next Steps

1. **Copy prompt file** → `AI_AGENT_CLAUDE_CODE_PROMPT.txt`
2. **Open Claude Code** → Load JARVIS system prompt
3. **Paste prompt** → Into Claude Code input
4. **Generate code** → Claude Code generates 6,000+ lines
5. **Review** → Check generated services, models, tests
6. **Run tests** → `pytest jarvis/ai_agent/tests/ -v --cov`
7. **Commit** → `git commit -m "feat: Add AI Agent module with RAG and multi-provider LLM support"`
8. **Deploy** → Configure API keys, set up database, run in production

## Support & Documentation

- **Specification**: `AI_AGENT_MODULE_SPECIFICATION.md`
- **Prompt**: `AI_AGENT_CLAUDE_CODE_PROMPT.txt`
- **Code**: Generated in `jarvis/ai_agent/`
- **Tests**: Generated in `jarvis/ai_agent/tests/`
- **Config**: `.claude-code/config.json`

## Estimated Timeline

| Task | Time | Status |
|------|------|--------|
| Copy API keys to `.env` | 5 min | Ready |
| Update `config.json` | 10 min | Ready |
| Generate code (Claude Code) | 5-10 min | Pending |
| Review generated code | 30 min | Pending |
| Run tests | 5 min | Pending |
| Setup database | 10 min | Pending |
| Integration test | 15 min | Pending |
| **Total** | **~90 minutes** | **Pending** |

---

**Ready to generate?**

1. Paste `AI_AGENT_CLAUDE_CODE_PROMPT.txt` into Claude Code
2. Press generate
3. Wait ~5 minutes for code generation
4. Review the output
5. Approve and commit

Your AI Agent is ready to serve your JARVIS platform! 🚀
