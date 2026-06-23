# BAB AI Financial Analysis — Design Spec

## Goal
Add a Big 4-style AI financial analysis tab to BAB Controlling that auto-generates profitability, variance, benchmark, and risk analysis using Claude API, plus a prompt box for ad-hoc questions about the data.

## Architecture
- Backend: Single POST endpoint `/controlling/bab/api/analyze` proxies Claude API with structured financial data context
- Frontend: New "Analiză" tab in Controlling with auto-insights panel + prompt box
- AI Model: Claude Sonnet via Anthropic API (speed/cost balance)
- No streaming v1 — full response returned

## Backend

### Endpoint: `POST /controlling/bab/api/analyze`

**Request:**
```json
{
  "company_id": 12,
  "mode": "auto" | "query",
  "prompt": "string (query mode only)",
  "cross_company": false
}
```

**Response:**
```json
{
  "success": true,
  "analysis": "markdown string",
  "tokens_used": 1234
}
```

**Flow:**
1. Fetch all uploads + reports for company_id (reuse `compute_marja_report`)
2. Build data context as formatted text tables (months × indicators, EUR + LEI)
3. If `cross_company=true`, include all companies with BAB data
4. Build Claude prompt:
   - **Auto mode**: Big 4 analysis template covering profitability trends, variance analysis, cost structure, cross-company benchmarks, risk flags, opportunities
   - **Query mode**: User prompt + same data context
5. Call Claude API with `claude-sonnet-4-5-20250514`
6. Return markdown response + token count

**Claude API integration:**
- Use `anthropic` Python SDK (already in requirements or add it)
- API key from environment variable `ANTHROPIC_API_KEY`
- Max tokens: 4096 for auto, 2048 for query
- System prompt establishes Big 4 financial analyst persona

**Auto-analysis prompt template sections:**
1. Profitability Analysis — margin trends, margin % if revenue available
2. Variance Analysis — MoM changes, biggest movers up/down
3. Cost Structure — which konto groups drive costs
4. Cross-Company Benchmark — compare margins across companies (if cross_company)
5. Risk Flags — declining trends, negative margins, anomalies
6. Opportunities — improving segments, growth areas

**File:** `jarvis/accounting/controlling_bab/ai_analysis.py` — builds prompts, calls Claude
**Route:** Added to `jarvis/accounting/controlling_bab/routes.py`

## Frontend

### New tab: "Analiză"
Added as 4th tab after Configurare in the Controlling page.

**Layout:**
1. Header: "Analiză Financiară AI" + "Generează analiză" button + checkbox "Include toate companiile"
2. Auto-insights panel: Renders markdown. Empty state before first generation. Loading spinner during API call.
3. Divider
4. Prompt section: "Întreabă despre date" header + text input + "Trimite" button
5. Q&A history: Session-state array of `{prompt, response}` pairs rendered as chat bubbles

**Markdown rendering:** Use `react-markdown` (or existing markdown renderer if present in project)

**Data scope:** Defaults to current company. Cross-company checkbox adds all companies' data to the AI context.

**State:**
- `autoAnalysis: string | null` — cached auto-analysis response
- `autoLoading: boolean`
- `queryHistory: { prompt: string; response: string }[]`
- `queryLoading: boolean`
- `crossCompany: boolean`

**API client:** Add `analyze` method to `controllingApi` in `jarvis/frontend/src/api/controlling.ts`

## Constraints
- API key stored as env var, never exposed to frontend
- Permission check: reuse existing `_check_bab_perm('view')`
- Rate limiting: none for v1 (internal tool, few users)
- Language: Romanian for analysis output (prompt instructs Romanian)
- Cost: ~$0.01-0.03 per analysis call with Sonnet
