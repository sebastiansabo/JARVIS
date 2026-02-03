-- ============================================================
-- AI Agent Module Database Schema
--
-- Run this migration to create the ai_agent schema and tables.
-- Requires PostgreSQL 12+ and pgvector extension for RAG.
-- ============================================================

-- Create ai_agent schema for isolation
CREATE SCHEMA IF NOT EXISTS ai_agent;

-- Try to enable pgvector extension (may fail if not installed)
-- If this fails, RAG will use fallback text search
DO $$
BEGIN
    CREATE EXTENSION IF NOT EXISTS vector;
EXCEPTION WHEN OTHERS THEN
    RAISE NOTICE 'pgvector extension not available - RAG will use text search fallback';
END
$$;

-- ============================================================
-- Model Configurations (LLM providers)
-- ============================================================

CREATE TABLE IF NOT EXISTS ai_agent.model_configs (
    id SERIAL PRIMARY KEY,
    provider VARCHAR(50) NOT NULL,           -- claude, openai, gemini, groq, local
    model_name VARCHAR(100) NOT NULL,        -- claude-sonnet-4-20250514, gpt-4, etc.
    display_name VARCHAR(100),               -- User-friendly name
    api_key_encrypted TEXT,                  -- Encrypted API key (NULL for local/env-based)
    base_url VARCHAR(255),                   -- Custom endpoint (for local LLaMA)

    -- Pricing (per 1K tokens)
    cost_per_1k_input DECIMAL(10,6) DEFAULT 0,
    cost_per_1k_output DECIMAL(10,6) DEFAULT 0,

    -- Limits
    max_tokens INTEGER DEFAULT 4096,
    rate_limit_rpm INTEGER DEFAULT 60,       -- Requests per minute
    rate_limit_tpm INTEGER DEFAULT 100000,   -- Tokens per minute

    -- Settings
    default_temperature DECIMAL(3,2) DEFAULT 0.7,
    is_active BOOLEAN DEFAULT TRUE,
    is_default BOOLEAN DEFAULT FALSE,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Only one default model per provider
CREATE UNIQUE INDEX IF NOT EXISTS idx_model_configs_default
ON ai_agent.model_configs (provider)
WHERE is_default = TRUE;

-- ============================================================
-- Conversations (chat sessions)
-- ============================================================

CREATE TABLE IF NOT EXISTS ai_agent.conversations (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(255),                       -- Auto-generated or user-set
    model_config_id INTEGER REFERENCES ai_agent.model_configs(id),

    -- Status
    status VARCHAR(20) DEFAULT 'active',      -- active, archived, deleted

    -- Aggregated stats (updated after each message)
    total_tokens INTEGER DEFAULT 0,
    total_cost DECIMAL(10,4) DEFAULT 0,
    message_count INTEGER DEFAULT 0,

    -- Metadata
    metadata JSONB DEFAULT '{}',              -- Flexible storage for context

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    archived_at TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conversations_user ON ai_agent.conversations(user_id);
CREATE INDEX IF NOT EXISTS idx_conversations_status ON ai_agent.conversations(status);
CREATE INDEX IF NOT EXISTS idx_conversations_created ON ai_agent.conversations(created_at DESC);

-- ============================================================
-- Messages (individual chat messages)
-- ============================================================

CREATE TABLE IF NOT EXISTS ai_agent.messages (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER NOT NULL REFERENCES ai_agent.conversations(id) ON DELETE CASCADE,

    -- Message content
    role VARCHAR(20) NOT NULL,                -- user, assistant, system
    content TEXT NOT NULL,

    -- Token tracking
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    cost DECIMAL(10,6) DEFAULT 0,

    -- RAG sources cited
    rag_sources JSONB DEFAULT '[]',           -- [{doc_id, score, snippet}, ...]

    -- Model used (may differ from conversation default)
    model_config_id INTEGER REFERENCES ai_agent.model_configs(id),

    -- Timing
    response_time_ms INTEGER,                 -- How long the LLM took

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_messages_conversation ON ai_agent.messages(conversation_id);
CREATE INDEX IF NOT EXISTS idx_messages_created ON ai_agent.messages(created_at);

-- ============================================================
-- RAG Documents (indexed JARVIS data)
-- ============================================================

-- Check if vector type exists (pgvector installed)
DO $$
BEGIN
    -- Try to create table with vector column
    CREATE TABLE IF NOT EXISTS ai_agent.rag_documents (
        id SERIAL PRIMARY KEY,

        -- Source identification
        source_type VARCHAR(50) NOT NULL,         -- invoice, transaction, company, employee
        source_id INTEGER,                        -- FK to source table (invoice_id, etc.)
        source_table VARCHAR(100),                -- invoices, bank_statement_transactions, etc.

        -- Content
        content TEXT NOT NULL,                    -- Searchable text content
        content_hash VARCHAR(64),                 -- SHA256 to detect changes

        -- Vector embedding (1536 dimensions for text-embedding-3-small)
        embedding vector(1536),

        -- Metadata for filtering
        metadata JSONB DEFAULT '{}',              -- {company, date, amount, etc.}

        -- Security
        company_id INTEGER REFERENCES companies(id),  -- For access control

        -- Status
        is_active BOOLEAN DEFAULT TRUE,

        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );

    -- Vector similarity search index (IVFFlat for good balance)
    CREATE INDEX IF NOT EXISTS idx_rag_documents_embedding
    ON ai_agent.rag_documents
    USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

EXCEPTION WHEN undefined_object THEN
    -- pgvector not available, create table without vector column
    RAISE NOTICE 'Creating rag_documents without vector support (pgvector not installed)';

    CREATE TABLE IF NOT EXISTS ai_agent.rag_documents (
        id SERIAL PRIMARY KEY,
        source_type VARCHAR(50) NOT NULL,
        source_id INTEGER,
        source_table VARCHAR(100),
        content TEXT NOT NULL,
        content_hash VARCHAR(64),
        -- No embedding column - will use text search
        metadata JSONB DEFAULT '{}',
        company_id INTEGER REFERENCES companies(id),
        is_active BOOLEAN DEFAULT TRUE,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
END
$$;

CREATE INDEX IF NOT EXISTS idx_rag_documents_source ON ai_agent.rag_documents(source_type, source_id);
CREATE INDEX IF NOT EXISTS idx_rag_documents_company ON ai_agent.rag_documents(company_id);
CREATE INDEX IF NOT EXISTS idx_rag_documents_active ON ai_agent.rag_documents(is_active) WHERE is_active = TRUE;

-- Full-text search index (fallback when pgvector not available)
CREATE INDEX IF NOT EXISTS idx_rag_documents_content_fts
ON ai_agent.rag_documents
USING gin(to_tsvector('english', content));

-- ============================================================
-- Conversation Context (query analysis cache)
-- ============================================================

CREATE TABLE IF NOT EXISTS ai_agent.conversation_contexts (
    id SERIAL PRIMARY KEY,
    message_id INTEGER NOT NULL REFERENCES ai_agent.messages(id) ON DELETE CASCADE,

    -- Analysis results
    extracted_entities JSONB DEFAULT '{}',    -- {dates, amounts, companies, etc.}
    detected_intent VARCHAR(50),              -- query, analysis, report, action
    confidence DECIMAL(3,2),

    -- RAG retrieval
    rag_query TEXT,                           -- Optimized search query
    rag_results JSONB DEFAULT '[]',           -- Retrieved document IDs and scores

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_contexts_message ON ai_agent.conversation_contexts(message_id);

-- ============================================================
-- Conversation Logs (audit trail)
-- ============================================================

CREATE TABLE IF NOT EXISTS ai_agent.conversation_logs (
    id SERIAL PRIMARY KEY,
    conversation_id INTEGER REFERENCES ai_agent.conversations(id) ON DELETE SET NULL,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,

    action VARCHAR(50) NOT NULL,              -- created, message_sent, archived, deleted
    details JSONB DEFAULT '{}',

    ip_address VARCHAR(45),
    user_agent TEXT,

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_conversation_logs_conv ON ai_agent.conversation_logs(conversation_id);
CREATE INDEX IF NOT EXISTS idx_conversation_logs_user ON ai_agent.conversation_logs(user_id);
CREATE INDEX IF NOT EXISTS idx_conversation_logs_created ON ai_agent.conversation_logs(created_at);

-- ============================================================
-- Seed Default Model Configurations
-- ============================================================

INSERT INTO ai_agent.model_configs (provider, model_name, display_name, cost_per_1k_input, cost_per_1k_output, max_tokens, is_default)
SELECT 'claude', 'claude-sonnet-4-20250514', 'Claude Sonnet (Fast)', 0.003, 0.015, 4096, TRUE
WHERE NOT EXISTS (SELECT 1 FROM ai_agent.model_configs WHERE provider = 'claude' AND model_name = 'claude-sonnet-4-20250514');

INSERT INTO ai_agent.model_configs (provider, model_name, display_name, cost_per_1k_input, cost_per_1k_output, max_tokens, is_default)
SELECT 'claude', 'claude-opus-4-5-20251101', 'Claude Opus (Smart)', 0.015, 0.075, 4096, FALSE
WHERE NOT EXISTS (SELECT 1 FROM ai_agent.model_configs WHERE provider = 'claude' AND model_name = 'claude-opus-4-5-20251101');

INSERT INTO ai_agent.model_configs (provider, model_name, display_name, cost_per_1k_input, cost_per_1k_output, max_tokens, is_default)
SELECT 'openai', 'gpt-4-turbo', 'GPT-4 Turbo', 0.01, 0.03, 4096, FALSE
WHERE NOT EXISTS (SELECT 1 FROM ai_agent.model_configs WHERE provider = 'openai' AND model_name = 'gpt-4-turbo');

INSERT INTO ai_agent.model_configs (provider, model_name, display_name, cost_per_1k_input, cost_per_1k_output, max_tokens, is_default)
SELECT 'openai', 'gpt-3.5-turbo', 'GPT-3.5 (Cheap)', 0.0005, 0.0015, 4096, FALSE
WHERE NOT EXISTS (SELECT 1 FROM ai_agent.model_configs WHERE provider = 'openai' AND model_name = 'gpt-3.5-turbo');

INSERT INTO ai_agent.model_configs (provider, model_name, display_name, cost_per_1k_input, cost_per_1k_output, max_tokens, is_default)
SELECT 'groq', 'mixtral-8x7b-32768', 'Mixtral (Ultra Fast)', 0.00027, 0.00027, 32768, FALSE
WHERE NOT EXISTS (SELECT 1 FROM ai_agent.model_configs WHERE provider = 'groq' AND model_name = 'mixtral-8x7b-32768');

INSERT INTO ai_agent.model_configs (provider, model_name, display_name, cost_per_1k_input, cost_per_1k_output, max_tokens, is_default)
SELECT 'groq', 'llama-3.3-70b-versatile', 'Llama 3.3 70B', 0.00059, 0.00079, 32768, FALSE
WHERE NOT EXISTS (SELECT 1 FROM ai_agent.model_configs WHERE provider = 'groq' AND model_name = 'llama-3.3-70b-versatile');

INSERT INTO ai_agent.model_configs (provider, model_name, display_name, cost_per_1k_input, cost_per_1k_output, max_tokens, is_default)
SELECT 'gemini', 'gemini-pro', 'Gemini Pro', 0.00025, 0.0005, 8192, FALSE
WHERE NOT EXISTS (SELECT 1 FROM ai_agent.model_configs WHERE provider = 'gemini' AND model_name = 'gemini-pro');

-- ============================================================
-- Add AI Agent to Module Menu
-- ============================================================

-- Insert AI Agent module into module_menu_items if not exists
INSERT INTO module_menu_items (module_key, name, description, icon, url, color, status, sort_order)
SELECT 'ai_agent', 'AI Agent', 'Chat assistant with RAG', 'bi-robot', '/ai-agent/', '#6f42c1', 'active', 2
WHERE NOT EXISTS (SELECT 1 FROM module_menu_items WHERE module_key = 'ai_agent');

-- ============================================================
-- Done
-- ============================================================

-- Verify installation
DO $$
DECLARE
    v_has_vector BOOLEAN;
BEGIN
    -- Check if vector type exists
    SELECT EXISTS (
        SELECT 1 FROM pg_type WHERE typname = 'vector'
    ) INTO v_has_vector;

    IF v_has_vector THEN
        RAISE NOTICE 'AI Agent schema created with pgvector support (semantic RAG enabled)';
    ELSE
        RAISE NOTICE 'AI Agent schema created without pgvector (using text search fallback)';
    END IF;
END
$$;
