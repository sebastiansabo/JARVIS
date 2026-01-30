# AI Agent Module (Conversational RAG) - Technical Specification

**Status**: Ready for Claude Code  
**Coverage**: 75% minimum  
**Prompt File**: `/Users/sebastiansabo/Documents/Git/Bugetare/jarvis/AI_AGENT_CLAUDE_CODE_PROMPT.txt`  

## Overview

AI Agent Module provides a conversational AI chatbot interface to JARVIS data using Retrieval Augmented Generation (RAG). The AI agent:

- **Answers questions about JARVIS data** (invoices, transactions, GL, reports, etc.)
- **Uses semantic search** (RAG) to find relevant data
- **Supports multiple AI models** (Claude, ChatGPT, Gemini, Groq, Local LLaMA)
- **Maintains conversation context** (remembers prior questions)
- **Respects data authorization** (only returns data user can access)
- **Tracks costs & usage** (which model, how many tokens, cost per response)

## Core Concept: RAG (Retrieval Augmented Generation)

Without RAG (wrong approach):
```
User: "What invoices from ACME did we have in January?"
AI: "Based on my training data (from 2024), ACME is a company..."
❌ Generic knowledge. No actual JARVIS data.
```

With RAG (correct approach):
```
User: "What invoices from ACME did we have in January?"

1. RAG Search: Find similar documents in JARVIS
   → Finds: Invoice from ACME (€5,000, Jan 15), Invoice from ACME (€3,000, Jan 8)

2. AI Responds with RAG data:
   "You had 2 invoices from ACME in January totaling €8,000:
    - €5,000 on January 15
    - €3,000 on January 8"
    
✅ Specific to your JARVIS data. Backed by RAG sources.
```

## What Gets Generated

### Services (10 total)

1. **AIAgentService** (400+ lines)
   - `create_conversation()` - Start new chat
   - `send_message()` - User message → AI response
   - `get_conversation_history()` - Load past messages
   - `archive_conversation()` - Store conversation

2. **RAGService** (350+ lines)
   - `index_rag_documents()` - Build RAG index from JARVIS data
   - `search_rag()` - Find relevant documents by semantic similarity
   - Vector embedding & search

3. **EmbeddingService** (200+ lines)
   - `generate_embedding()` - Convert text to vector
   - `batch_generate_embeddings()` - Process multiple documents
   - Support OpenAI, Cohere, local models

4. **ContextManagementService** (250+ lines)
   - `extract_entities()` - Pull out amounts, dates, names
   - `determine_intent()` - Is this a query, analysis, report request?
   - `build_conversation_context()` - Prepare context for LLM

5. **ModelProviderService** (300+ lines)
   - `call_model()` - Unified interface to all LLM providers
   - Support Claude, OpenAI, Google, Groq, Local LLaMA
   - Token usage & cost tracking

6. **SecurityService** (150+ lines)
   - `check_data_access()` - User can see this data?
   - `filter_rag_results()` - Only return authorized data

7. **ConversationAnalyticsService** (150+ lines)
   - `track_message_metrics()` - Response time, cost, tokens
   - `get_usage_analytics()` - Aggregate usage by user, model, etc.

8. **AIAgentScheduler** (100+ lines)
   - `reindex_rag_nightly()` - Keep RAG index fresh
   - `cleanup_old_conversations()` - Archive old chats

### Data Models

```
ModelConfig ─→ AI Model credentials & settings
               - API keys (encrypted)
               - Model name (claude-opus, gpt-4, gemini-pro, etc.)
               - Rate limits (RPM, TPM)
               - Pricing info (cost per 1K tokens)

Conversation ─→ Chat session
                - User who created it
                - Messages (user + assistant)
                - Model used
                - Total tokens & cost
                - Status (ACTIVE, ARCHIVED)

Message ─→ Individual message
           - Sender (USER or ASSISTANT)
           - Content (what was said)
           - Tokens used (for cost tracking)
           - RAG sources cited (which JARVIS data was referenced)

RAGDocument ─→ Indexed JARVIS data
               - Source (invoice, transaction, GL posting, etc.)
               - Content (extractable text)
               - Embedding (vector for semantic search)
               - Metadata (amounts, dates, entities)

ConversationContext ─→ Track query context
                       - User query
                       - Extracted entities
                       - Intent classification
                       - RAG results retrieved
```

## Integration Architecture

```
┌──────────────────────────────────────────────────────┐
│              User Chat Interface                     │
│         (Web, Mobile, API, Embedded)                │
└──────────────────────────┬──────────────────────────┘
                           │
                           ↓
              ┌────────────────────────┐
              │ AIAgentService         │
              │ - manage conversation  │
              │ - orchestrate flow     │
              └────────────┬───────────┘
                           │
         ┌─────────────────┼─────────────────┐
         ↓                 ↓                 ↓
    ┌────────────┐  ┌──────────────┐  ┌────────────┐
    │ RAGService │  │ Context      │  │ Security   │
    │ - search   │  │ Management   │  │ - check    │
    │ - retrieve │  │ - entities   │  │   access   │
    │   data     │  │ - intent     │  │ - filter   │
    └─────┬──────┘  └──────────────┘  │   results  │
          │                            └────────────┘
          │
          ↓
    ┌────────────────────┐
    │ JARVIS Modules     │
    │ (Read-only access) │
    ├────────────────────┤
    │ - invoicing        │
    │ - bank_import      │
    │ - accounting_core  │
    │ - reconciliation   │
    │ - reporting        │
    │ - vendors, etc.    │
    └────────────────────┘
         │
         ↓
    ┌────────────────────┐
    │ RAG Index          │
    │ (Vector DB)        │
    │                    │
    │ 100K+ documents    │
    │ With embeddings    │
    └────────────────────┘
         │
         ↓
    ┌────────────────────┐
    │ ModelProviderSvc   │
    │ - Claude API       │
    │ - OpenAI API       │
    │ - Google API       │
    │ - Groq API         │
    │ - Local LLaMA      │
    └────────────────────┘
         │
         ↓
    ┌────────────────────┐
    │ AI Response        │
    │ (Backed by RAG)    │
    │ "You had 2 ACME    │
    │  invoices for €8K" │
    └────────────────────┘
```

## Model Support

### Supported Providers

1. **Claude** (Anthropic)
   - Model: `claude-opus-4-5-20251101` (best), `claude-sonnet-4-5` (fast), `claude-haiku` (cheap)
   - Cost: $0.015-0.075 per 1K tokens
   - Pros: Smart, good at reasoning
   - Cons: Slightly more expensive

2. **OpenAI (ChatGPT)**
   - Model: `gpt-4` (best), `gpt-4-turbo` (balanced), `gpt-3.5-turbo` (cheap)
   - Cost: $0.03-0.06 per 1K tokens
   - Pros: Most popular, good ecosystem
   - Cons: Requires API key management

3. **Google (Gemini)**
   - Model: `gemini-pro` (best), `gemini-pro-vision` (with images)
   - Cost: Competitive
   - Pros: Free tier available
   - Cons: Still relatively new

4. **Groq**
   - Model: `mixtral-8x7b-32768`, `llama-2-70b`
   - Cost: Very cheap
   - Pros: Ultra-fast inference
   - Cons: Open models may be less sophisticated

5. **Local LLaMA** (Self-hosted)
   - Model: `mistral`, `neural-chat`, `orca-mini`
   - Cost: Zero (runs on your hardware)
   - Pros: No API costs, private
   - Cons: Requires compute resources, slower

## Example Conversation Flow

```
User: "What was our biggest expense last month?"

1. AIAgentService.send_message()

2. Extract entities:
   - Timeframe: "last month" (Jan 2026)
   - Intent: ANALYSIS (calculate/summarize)

3. RAG search:
   - Query: "biggest expense January 2026"
   - Find similar documents:
     * GL posting: Salary expense €25,000 (high match)
     * GL posting: COGS €20,000 (match)
     * Invoice: ACME €5,000 (match)

4. Build context:
   - System prompt
   - Conversation history (if any)
   - Top 5 RAG results

5. Call ModelProviderService:
   - Model: Claude Opus
   - Prompt: "Based on JARVIS data: [RAG results]"
   - Get response: "Your biggest expense last month was 
                   Salaries at €25,000..."

6. Create Message records:
   - User message: "What was our biggest expense..."
   - Assistant message: "Your biggest expense..."
   - Tokens: 150 input, 80 output
   - Cost: €0.0034

7. Return response with RAG sources cited
```

## Cost Model

Every response tracked:

```
Cost = (input_tokens / 1000 * cost_per_1k_input) 
      + (output_tokens / 1000 * cost_per_1k_output)

Example (Claude Opus):
  Input: 200 tokens @ $0.015/1K = $0.003
  Output: 100 tokens @ $0.075/1K = $0.0075
  Total: $0.0105 per response

Annual cost (100 conversations, 10 messages each):
  1000 responses * $0.01 = ~$10/month (very cheap)
```

## Security Model

### Data Authorization

```
User: Finance Manager
Authorized: All financial data
Denied: None

User: Vendor Manager
Authorized: Vendor data, related invoices
Denied: GL postings, salary info

When user asks: "Show all invoices"
→ Return all invoices they can see
→ Filter out invoices they can't access
→ Remove sensitive fields if not authorized
```

### API Key Protection

- API keys stored encrypted in database
- Never logged or exposed in error messages
- Rotated regularly
- Rate-limited per user

## Performance Targets

- **Response generation**: < 5 seconds
- **RAG search**: < 1 second
- **Embedding generation**: < 500ms
- **Message retrieval**: < 100ms

## Example Responses

### Query Type: Data Lookup

```
User: "How much did we pay ACME in January?"

AI: "According to JARVIS invoices from January 2026, 
    you had two transactions with ACME:
    
    • Invoice on January 8: €3,000 (office supplies)
    • Invoice on January 15: €5,000 (equipment)
    
    Total: €8,000
    
    Source: 2 invoices from ACME Corp (invoice-ids: inv-001, inv-002)"
```

### Analysis Type: Financial Analysis

```
User: "What's our cash position?"

AI: "Based on current GL data in JARVIS:
    
    Cash on Hand: €50,000
    Outstanding Receivables: €82,000
    Projected Collections (30 days): €55,000
    
    Outstanding Payables: €80,000
    Projected Payments (30 days): €45,000
    
    Expected Cash Position (30 days): €60,000
    
    Status: ✅ Healthy (positive balance)
    
    Source: GL bank account (1010), reconciliation data, aging reports"
```

### Report Type

```
User: "Generate monthly P&L for January"

AI: "I can generate the monthly P&L report. Let me access 
    JARVIS reporting module..."
    
→ Calls reporting service
→ Generates P&L
→ Exports as PDF
→ Sends link

"✅ Monthly P&L Report Generated
 
 January 2026 Income Statement
 Revenue: €142,000
 Expenses: €117,500
 Net Income: €24,300
 
 📄 Download: [link to PDF]"
```

## Configuration Example

```json
{
  "ai_agent_settings": {
    "default_provider": "CLAUDE",
    "default_model": "claude-opus-4-5-20251101",
    "rag_enabled": true,
    "rag_embedding_model": "text-embedding-3-small",
    "rate_limit_rpm": 60,
    "rate_limit_tpm": 90000,
    "model_configs": {
      "claude": {
        "api_key": "sk-ant-...",
        "max_tokens": 2048,
        "temperature": 0.7,
        "cost_per_1k_input": 0.015,
        "cost_per_1k_output": 0.075
      },
      "openai": {
        "api_key": "sk-...",
        "model_name": "gpt-4",
        "cost_per_1k_input": 0.03,
        "cost_per_1k_output": 0.06
      },
      "groq": {
        "api_key": "gsk_...",
        "model_name": "mixtral-8x7b",
        "cost_per_1k_input": 0.0005,
        "cost_per_1k_output": 0.0015
      }
    }
  }
}
```

## What Success Looks Like

✅ User asks questions about JARVIS data in natural language
✅ AI retrieves relevant data via RAG
✅ AI responds with accurate information from JARVIS
✅ Response includes source citations (which invoices, GL accounts, etc.)
✅ User can switch between models (Claude for smart analysis, Groq for speed)
✅ Cost per response tracked (typically $0.01-0.05)
✅ Conversation history preserved (can ask follow-up questions)
✅ Unauthorized data never returned (security enforced)
✅ Works for all JARVIS data (invoices, GL, reports, etc.)
✅ Reduces manual data lookup by 80%

## Next Steps

1. Open Claude Code in `/jarvis` directory
2. Load system prompt: `.claude-code/system_prompt.md`
3. Paste `AI_AGENT_CLAUDE_CODE_PROMPT.txt` into Claude Code
4. Claude Code generates:
   - 10 services (2,000+ lines)
   - RAG indexing
   - Model provider abstraction
   - Security layer
   - 8 test files (1,200+ tests)
   - Validation hooks
5. Review generated code
6. Run tests (should see 75%+ coverage)
7. Commit to git

## Module Dependencies

```
ai_agent READS:
  ├─ invoicing (Invoice) - for query data
  ├─ bank_import (Transaction) - for query data
  ├─ accounting_core (GL, Accounts) - for query data
  ├─ reconciliation (Reconciliation) - for status
  ├─ reporting (Reports) - for export
  └─ all modules (read-only)

ai_agent WRITES:
  ├─ Self (Conversation, Message, RAGDocument)
  ├─ ModelConfig (AI settings)
  └─ audit (ConversationLog)

ai_agent USED BY:
  └─ Users (via chat interface)
```

## Estimated Code Generation

**Total lines of code**: ~6,500
- Services: 1,800 lines
- RAG & embedding: 700 lines
- Model providers: 600 lines
- Models: 300 lines
- Repositories: 250 lines
- Tests: 2,000+ lines
- Configuration: 200 lines

**Time to generate**: ~5-10 minutes
**Time to test**: ~30 seconds
**Review time**: ~30 minutes

## Order of Deployment

**Recommended: Deploy after GL Posting + Reconciliation + Reporting**

Reason: AI agent will be more useful if it can query fully functional GL, reconciliation, and reporting data.

But can also deploy sooner if needed (will just have less data to query).

---

**Ready to generate**: Yes  
**Prompt updated**: 2026-01-29  
**Status**: Complete specification ✅
