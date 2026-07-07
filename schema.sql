--
-- PostgreSQL database dump
--

\restrict rQ5wibgOns0oFgQ80cIMJS7B6qWQCd7L8BUV5Mrg1riCZnlfeudMLU6k13OOxcp

-- Dumped from database version 18.1
-- Dumped by pg_dump version 18.2 (Homebrew)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

--
-- Name: ai_agent; Type: SCHEMA; Schema: -; Owner: doadmin
--

CREATE SCHEMA ai_agent;


ALTER SCHEMA ai_agent OWNER TO doadmin;

--
-- Name: hr; Type: SCHEMA; Schema: -; Owner: doadmin
--

CREATE SCHEMA hr;


ALTER SCHEMA hr OWNER TO doadmin;

--
-- Name: public; Type: SCHEMA; Schema: -; Owner: doadmin
--

-- *not* creating schema, since initdb creates it


ALTER SCHEMA public OWNER TO doadmin;

--
-- Name: SCHEMA public; Type: COMMENT; Schema: -; Owner: doadmin
--

COMMENT ON SCHEMA public IS '';


--
-- Name: pg_trgm; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS pg_trgm WITH SCHEMA public;


--
-- Name: EXTENSION pg_trgm; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION pg_trgm IS 'text similarity measurement and index searching based on trigrams';


--
-- Name: vector; Type: EXTENSION; Schema: -; Owner: -
--

CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;


--
-- Name: EXTENSION vector; Type: COMMENT; Schema: -; Owner: 
--

COMMENT ON EXTENSION vector IS 'vector data type and ivfflat and hnsw access methods';


--
-- Name: permission_scope; Type: TYPE; Schema: public; Owner: doadmin
--

CREATE TYPE public.permission_scope AS ENUM (
    'deny',
    'own',
    'department',
    'all'
);


ALTER TYPE public.permission_scope OWNER TO doadmin;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: conversation_contexts; Type: TABLE; Schema: ai_agent; Owner: doadmin
--

CREATE TABLE ai_agent.conversation_contexts (
    id integer NOT NULL,
    message_id integer NOT NULL,
    extracted_entities jsonb DEFAULT '{}'::jsonb,
    detected_intent character varying(50),
    confidence numeric(3,2),
    rag_query text,
    rag_results jsonb DEFAULT '[]'::jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE ai_agent.conversation_contexts OWNER TO doadmin;

--
-- Name: conversation_contexts_id_seq; Type: SEQUENCE; Schema: ai_agent; Owner: doadmin
--

CREATE SEQUENCE ai_agent.conversation_contexts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ai_agent.conversation_contexts_id_seq OWNER TO doadmin;

--
-- Name: conversation_contexts_id_seq; Type: SEQUENCE OWNED BY; Schema: ai_agent; Owner: doadmin
--

ALTER SEQUENCE ai_agent.conversation_contexts_id_seq OWNED BY ai_agent.conversation_contexts.id;


--
-- Name: conversation_logs; Type: TABLE; Schema: ai_agent; Owner: doadmin
--

CREATE TABLE ai_agent.conversation_logs (
    id integer NOT NULL,
    conversation_id integer,
    user_id integer,
    action character varying(50) NOT NULL,
    details jsonb DEFAULT '{}'::jsonb,
    ip_address character varying(45),
    user_agent text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE ai_agent.conversation_logs OWNER TO doadmin;

--
-- Name: conversation_logs_id_seq; Type: SEQUENCE; Schema: ai_agent; Owner: doadmin
--

CREATE SEQUENCE ai_agent.conversation_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ai_agent.conversation_logs_id_seq OWNER TO doadmin;

--
-- Name: conversation_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: ai_agent; Owner: doadmin
--

ALTER SEQUENCE ai_agent.conversation_logs_id_seq OWNED BY ai_agent.conversation_logs.id;


--
-- Name: conversations; Type: TABLE; Schema: ai_agent; Owner: doadmin
--

CREATE TABLE ai_agent.conversations (
    id integer NOT NULL,
    user_id integer,
    title character varying(255),
    model_config_id integer,
    status character varying(20) DEFAULT 'active'::character varying,
    total_tokens integer DEFAULT 0,
    total_cost numeric(10,4) DEFAULT 0,
    message_count integer DEFAULT 0,
    metadata jsonb DEFAULT '{}'::jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    archived_at timestamp without time zone
);


ALTER TABLE ai_agent.conversations OWNER TO doadmin;

--
-- Name: conversations_id_seq; Type: SEQUENCE; Schema: ai_agent; Owner: doadmin
--

CREATE SEQUENCE ai_agent.conversations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ai_agent.conversations_id_seq OWNER TO doadmin;

--
-- Name: conversations_id_seq; Type: SEQUENCE OWNED BY; Schema: ai_agent; Owner: doadmin
--

ALTER SEQUENCE ai_agent.conversations_id_seq OWNED BY ai_agent.conversations.id;


--
-- Name: messages; Type: TABLE; Schema: ai_agent; Owner: doadmin
--

CREATE TABLE ai_agent.messages (
    id integer NOT NULL,
    conversation_id integer NOT NULL,
    role character varying(20) NOT NULL,
    content text NOT NULL,
    input_tokens integer DEFAULT 0,
    output_tokens integer DEFAULT 0,
    cost numeric(10,6) DEFAULT 0,
    rag_sources jsonb DEFAULT '[]'::jsonb,
    model_config_id integer,
    response_time_ms integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE ai_agent.messages OWNER TO doadmin;

--
-- Name: messages_id_seq; Type: SEQUENCE; Schema: ai_agent; Owner: doadmin
--

CREATE SEQUENCE ai_agent.messages_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ai_agent.messages_id_seq OWNER TO doadmin;

--
-- Name: messages_id_seq; Type: SEQUENCE OWNED BY; Schema: ai_agent; Owner: doadmin
--

ALTER SEQUENCE ai_agent.messages_id_seq OWNED BY ai_agent.messages.id;


--
-- Name: model_configs; Type: TABLE; Schema: ai_agent; Owner: doadmin
--

CREATE TABLE ai_agent.model_configs (
    id integer NOT NULL,
    provider character varying(50) NOT NULL,
    model_name character varying(100) NOT NULL,
    display_name character varying(100),
    api_key_encrypted text,
    base_url character varying(255),
    cost_per_1k_input numeric(10,6) DEFAULT 0,
    cost_per_1k_output numeric(10,6) DEFAULT 0,
    max_tokens integer DEFAULT 4096,
    rate_limit_rpm integer DEFAULT 60,
    rate_limit_tpm integer DEFAULT 100000,
    default_temperature numeric(3,2) DEFAULT 0.7,
    is_active boolean DEFAULT true,
    is_default boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE ai_agent.model_configs OWNER TO doadmin;

--
-- Name: model_configs_id_seq; Type: SEQUENCE; Schema: ai_agent; Owner: doadmin
--

CREATE SEQUENCE ai_agent.model_configs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ai_agent.model_configs_id_seq OWNER TO doadmin;

--
-- Name: model_configs_id_seq; Type: SEQUENCE OWNED BY; Schema: ai_agent; Owner: doadmin
--

ALTER SEQUENCE ai_agent.model_configs_id_seq OWNED BY ai_agent.model_configs.id;


--
-- Name: rag_documents; Type: TABLE; Schema: ai_agent; Owner: doadmin
--

CREATE TABLE ai_agent.rag_documents (
    id integer NOT NULL,
    source_type character varying(50) NOT NULL,
    source_id integer,
    source_table character varying(100),
    content text NOT NULL,
    content_hash character varying(64),
    embedding public.vector(1536),
    metadata jsonb DEFAULT '{}'::jsonb,
    company_id integer,
    is_active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE ai_agent.rag_documents OWNER TO doadmin;

--
-- Name: rag_documents_id_seq; Type: SEQUENCE; Schema: ai_agent; Owner: doadmin
--

CREATE SEQUENCE ai_agent.rag_documents_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE ai_agent.rag_documents_id_seq OWNER TO doadmin;

--
-- Name: rag_documents_id_seq; Type: SEQUENCE OWNED BY; Schema: ai_agent; Owner: doadmin
--

ALTER SEQUENCE ai_agent.rag_documents_id_seq OWNED BY ai_agent.rag_documents.id;


--
-- Name: bonus_types; Type: TABLE; Schema: hr; Owner: doadmin
--

CREATE TABLE hr.bonus_types (
    id integer NOT NULL,
    name text NOT NULL,
    amount numeric(10,2) NOT NULL,
    days_per_amount numeric(5,2) DEFAULT 1,
    description text,
    is_active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE hr.bonus_types OWNER TO doadmin;

--
-- Name: bonus_types_id_seq; Type: SEQUENCE; Schema: hr; Owner: doadmin
--

CREATE SEQUENCE hr.bonus_types_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE hr.bonus_types_id_seq OWNER TO doadmin;

--
-- Name: bonus_types_id_seq; Type: SEQUENCE OWNED BY; Schema: hr; Owner: doadmin
--

ALTER SEQUENCE hr.bonus_types_id_seq OWNED BY hr.bonus_types.id;


--
-- Name: event_bonuses; Type: TABLE; Schema: hr; Owner: doadmin
--

CREATE TABLE hr.event_bonuses (
    id integer NOT NULL,
    user_id integer CONSTRAINT event_bonuses_employee_id_not_null NOT NULL,
    event_id integer NOT NULL,
    year integer NOT NULL,
    month integer NOT NULL,
    participation_start date,
    participation_end date,
    bonus_days numeric(3,1),
    hours_free integer,
    bonus_net numeric(10,2),
    details text,
    allocation_month text,
    created_by integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    bonus_type_id integer,
    responsable_id integer
);


ALTER TABLE hr.event_bonuses OWNER TO doadmin;

--
-- Name: event_bonuses_id_seq; Type: SEQUENCE; Schema: hr; Owner: doadmin
--

CREATE SEQUENCE hr.event_bonuses_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE hr.event_bonuses_id_seq OWNER TO doadmin;

--
-- Name: event_bonuses_id_seq; Type: SEQUENCE OWNED BY; Schema: hr; Owner: doadmin
--

ALTER SEQUENCE hr.event_bonuses_id_seq OWNED BY hr.event_bonuses.id;


--
-- Name: events; Type: TABLE; Schema: hr; Owner: doadmin
--

CREATE TABLE hr.events (
    id integer NOT NULL,
    name text NOT NULL,
    start_date date NOT NULL,
    end_date date NOT NULL,
    company text,
    brand text,
    description text,
    created_by integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE hr.events OWNER TO doadmin;

--
-- Name: events_id_seq; Type: SEQUENCE; Schema: hr; Owner: doadmin
--

CREATE SEQUENCE hr.events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE hr.events_id_seq OWNER TO doadmin;

--
-- Name: events_id_seq; Type: SEQUENCE OWNED BY; Schema: hr; Owner: doadmin
--

ALTER SEQUENCE hr.events_id_seq OWNED BY hr.events.id;


--
-- Name: allocations; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.allocations (
    id integer NOT NULL,
    invoice_id integer NOT NULL,
    company text NOT NULL,
    brand text,
    department text NOT NULL,
    subdepartment text,
    allocation_percent numeric(7,4) NOT NULL,
    allocation_value numeric(15,2) NOT NULL,
    responsible text,
    reinvoice_to text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    reinvoice_department text,
    reinvoice_subdepartment text,
    reinvoice_brand text,
    locked boolean DEFAULT false,
    comment text,
    responsible_user_id integer
);


ALTER TABLE public.allocations OWNER TO doadmin;

--
-- Name: allocations_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.allocations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.allocations_id_seq OWNER TO doadmin;

--
-- Name: allocations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.allocations_id_seq OWNED BY public.allocations.id;


--
-- Name: approval_audit_log; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.approval_audit_log (
    id integer NOT NULL,
    request_id integer NOT NULL,
    action text NOT NULL,
    actor_id integer,
    actor_type text DEFAULT 'user'::text,
    details jsonb DEFAULT '{}'::jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.approval_audit_log OWNER TO doadmin;

--
-- Name: approval_audit_log_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.approval_audit_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.approval_audit_log_id_seq OWNER TO doadmin;

--
-- Name: approval_audit_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.approval_audit_log_id_seq OWNED BY public.approval_audit_log.id;


--
-- Name: approval_decisions; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.approval_decisions (
    id integer NOT NULL,
    request_id integer NOT NULL,
    step_id integer NOT NULL,
    decided_by integer NOT NULL,
    decision text NOT NULL,
    comment text,
    delegated_to integer,
    delegation_reason text,
    conditions jsonb,
    decided_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_decision_type CHECK ((decision = ANY (ARRAY['approved'::text, 'rejected'::text, 'returned'::text, 'delegated'::text, 'abstained'::text])))
);


ALTER TABLE public.approval_decisions OWNER TO doadmin;

--
-- Name: approval_decisions_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.approval_decisions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.approval_decisions_id_seq OWNER TO doadmin;

--
-- Name: approval_decisions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.approval_decisions_id_seq OWNED BY public.approval_decisions.id;


--
-- Name: approval_delegations; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.approval_delegations (
    id integer NOT NULL,
    delegator_id integer NOT NULL,
    delegate_id integer NOT NULL,
    entity_type text,
    flow_id integer,
    starts_at timestamp without time zone NOT NULL,
    ends_at timestamp without time zone NOT NULL,
    reason text,
    is_active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.approval_delegations OWNER TO doadmin;

--
-- Name: approval_delegations_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.approval_delegations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.approval_delegations_id_seq OWNER TO doadmin;

--
-- Name: approval_delegations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.approval_delegations_id_seq OWNED BY public.approval_delegations.id;


--
-- Name: approval_flows; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.approval_flows (
    id integer NOT NULL,
    name text NOT NULL,
    slug text NOT NULL,
    description text,
    entity_type text NOT NULL,
    trigger_conditions jsonb DEFAULT '{}'::jsonb,
    is_active boolean DEFAULT true,
    priority integer DEFAULT 0,
    allow_parallel_steps boolean DEFAULT false,
    auto_approve_below numeric(15,2),
    auto_reject_after_hours integer,
    created_by integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.approval_flows OWNER TO doadmin;

--
-- Name: approval_flows_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.approval_flows_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.approval_flows_id_seq OWNER TO doadmin;

--
-- Name: approval_flows_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.approval_flows_id_seq OWNED BY public.approval_flows.id;


--
-- Name: approval_requests; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.approval_requests (
    id integer NOT NULL,
    entity_type text NOT NULL,
    entity_id integer NOT NULL,
    flow_id integer NOT NULL,
    current_step_id integer,
    status text DEFAULT 'pending'::text NOT NULL,
    context_snapshot jsonb DEFAULT '{}'::jsonb,
    requested_by integer NOT NULL,
    requested_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    resolved_at timestamp without time zone,
    resolution_note text,
    priority text DEFAULT 'normal'::text,
    due_by timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_approval_priority CHECK ((priority = ANY (ARRAY['low'::text, 'normal'::text, 'high'::text, 'urgent'::text]))),
    CONSTRAINT chk_approval_status CHECK ((status = ANY (ARRAY['pending'::text, 'in_progress'::text, 'approved'::text, 'rejected'::text, 'cancelled'::text, 'expired'::text, 'escalated'::text, 'on_hold'::text])))
);


ALTER TABLE public.approval_requests OWNER TO doadmin;

--
-- Name: approval_requests_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.approval_requests_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.approval_requests_id_seq OWNER TO doadmin;

--
-- Name: approval_requests_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.approval_requests_id_seq OWNED BY public.approval_requests.id;


--
-- Name: approval_steps; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.approval_steps (
    id integer NOT NULL,
    flow_id integer NOT NULL,
    name text NOT NULL,
    step_order integer NOT NULL,
    approver_type text NOT NULL,
    approver_user_id integer,
    approver_role_name text,
    requires_all boolean DEFAULT false,
    min_approvals integer DEFAULT 1,
    skip_conditions jsonb DEFAULT '{}'::jsonb,
    timeout_hours integer,
    escalation_step_id integer,
    escalation_user_id integer,
    notify_on_pending boolean DEFAULT true,
    notify_on_decision boolean DEFAULT true,
    reminder_after_hours integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.approval_steps OWNER TO doadmin;

--
-- Name: approval_steps_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.approval_steps_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.approval_steps_id_seq OWNER TO doadmin;

--
-- Name: approval_steps_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.approval_steps_id_seq OWNED BY public.approval_steps.id;


--
-- Name: auto_tag_rules; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.auto_tag_rules (
    id integer NOT NULL,
    name character varying(200) NOT NULL,
    entity_type character varying(30) NOT NULL,
    tag_id integer NOT NULL,
    conditions jsonb DEFAULT '[]'::jsonb NOT NULL,
    is_active boolean DEFAULT true,
    run_on_create boolean DEFAULT true,
    created_by integer,
    created_at timestamp without time zone DEFAULT now(),
    updated_at timestamp without time zone DEFAULT now(),
    match_mode character varying(10) DEFAULT 'all'::character varying NOT NULL
);


ALTER TABLE public.auto_tag_rules OWNER TO doadmin;

--
-- Name: auto_tag_rules_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.auto_tag_rules_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.auto_tag_rules_id_seq OWNER TO doadmin;

--
-- Name: auto_tag_rules_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.auto_tag_rules_id_seq OWNED BY public.auto_tag_rules.id;


--
-- Name: bank_statement_transactions; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.bank_statement_transactions (
    id integer NOT NULL,
    statement_id integer,
    statement_file text,
    company_name text,
    company_cui text,
    account_number text,
    transaction_date date,
    value_date date,
    description text,
    vendor_name text,
    matched_supplier text,
    amount numeric(15,2),
    currency text DEFAULT 'RON'::text,
    original_amount numeric(15,2),
    original_currency text,
    exchange_rate numeric(10,6),
    auth_code text,
    card_number text,
    transaction_type text,
    invoice_id integer,
    status text DEFAULT 'pending'::text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    suggested_invoice_id integer,
    match_confidence numeric(5,4),
    match_method text,
    merged_into_id integer,
    is_merged_result boolean DEFAULT false,
    merged_dates_display text
);


ALTER TABLE public.bank_statement_transactions OWNER TO doadmin;

--
-- Name: bank_statement_transactions_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.bank_statement_transactions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.bank_statement_transactions_id_seq OWNER TO doadmin;

--
-- Name: bank_statement_transactions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.bank_statement_transactions_id_seq OWNED BY public.bank_statement_transactions.id;


--
-- Name: bank_statements; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.bank_statements (
    id integer NOT NULL,
    filename text NOT NULL,
    file_hash text,
    company_name text,
    company_cui text,
    account_number text,
    period_from date,
    period_to date,
    total_transactions integer DEFAULT 0,
    new_transactions integer DEFAULT 0,
    duplicate_transactions integer DEFAULT 0,
    uploaded_by integer,
    uploaded_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.bank_statements OWNER TO doadmin;

--
-- Name: bank_statements_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.bank_statements_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.bank_statements_id_seq OWNER TO doadmin;

--
-- Name: bank_statements_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.bank_statements_id_seq OWNED BY public.bank_statements.id;


--
-- Name: brands; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.brands (
    id integer NOT NULL,
    name text NOT NULL,
    is_active boolean DEFAULT true
);


ALTER TABLE public.brands OWNER TO doadmin;

--
-- Name: brands_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.brands_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.brands_id_seq OWNER TO doadmin;

--
-- Name: brands_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.brands_id_seq OWNED BY public.brands.id;


--
-- Name: companies; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.companies (
    id integer NOT NULL,
    company text NOT NULL,
    brands text,
    vat text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.companies OWNER TO doadmin;

--
-- Name: companies_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.companies_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.companies_id_seq OWNER TO doadmin;

--
-- Name: companies_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.companies_id_seq OWNED BY public.companies.id;


--
-- Name: company_brands; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.company_brands (
    id integer NOT NULL,
    company_id integer NOT NULL,
    is_active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    brand_id integer
);


ALTER TABLE public.company_brands OWNER TO doadmin;

--
-- Name: company_brands_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.company_brands_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.company_brands_id_seq OWNER TO doadmin;

--
-- Name: company_brands_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.company_brands_id_seq OWNED BY public.company_brands.id;


--
-- Name: connector_sync_log; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.connector_sync_log (
    id integer NOT NULL,
    connector_id integer NOT NULL,
    sync_type text NOT NULL,
    status text NOT NULL,
    invoices_found integer DEFAULT 0,
    invoices_imported integer DEFAULT 0,
    error_message text,
    details jsonb DEFAULT '{}'::jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.connector_sync_log OWNER TO doadmin;

--
-- Name: connector_sync_log_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.connector_sync_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.connector_sync_log_id_seq OWNER TO doadmin;

--
-- Name: connector_sync_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.connector_sync_log_id_seq OWNED BY public.connector_sync_log.id;


--
-- Name: connectors; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.connectors (
    id integer NOT NULL,
    connector_type text NOT NULL,
    name text NOT NULL,
    status text DEFAULT 'disconnected'::text,
    config jsonb DEFAULT '{}'::jsonb,
    credentials jsonb DEFAULT '{}'::jsonb,
    last_sync timestamp without time zone,
    last_error text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.connectors OWNER TO doadmin;

--
-- Name: connectors_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.connectors_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.connectors_id_seq OWNER TO doadmin;

--
-- Name: connectors_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.connectors_id_seq OWNED BY public.connectors.id;


--
-- Name: department_structure; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.department_structure (
    id integer NOT NULL,
    company text NOT NULL,
    brand text,
    department text NOT NULL,
    subdepartment text,
    manager text,
    marketing text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    responsable_id integer,
    manager_ids integer[],
    marketing_ids integer[],
    cc_email text,
    company_id integer,
    manager_user_id integer
);


ALTER TABLE public.department_structure OWNER TO doadmin;

--
-- Name: department_structure_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.department_structure_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.department_structure_id_seq OWNER TO doadmin;

--
-- Name: department_structure_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.department_structure_id_seq OWNED BY public.department_structure.id;


--
-- Name: departments; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.departments (
    id integer NOT NULL,
    name text NOT NULL,
    is_active boolean DEFAULT true
);


ALTER TABLE public.departments OWNER TO doadmin;

--
-- Name: departments_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.departments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.departments_id_seq OWNER TO doadmin;

--
-- Name: departments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.departments_id_seq OWNED BY public.departments.id;


--
-- Name: dropdown_options; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.dropdown_options (
    id integer NOT NULL,
    dropdown_type text NOT NULL,
    value text NOT NULL,
    label text NOT NULL,
    color text,
    sort_order integer DEFAULT 0,
    is_active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    opacity numeric(3,2) DEFAULT 0.7,
    min_role text DEFAULT 'Viewer'::text,
    notify_on_status boolean DEFAULT false
);


ALTER TABLE public.dropdown_options OWNER TO doadmin;

--
-- Name: dropdown_options_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.dropdown_options_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.dropdown_options_id_seq OWNER TO doadmin;

--
-- Name: dropdown_options_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.dropdown_options_id_seq OWNED BY public.dropdown_options.id;


--
-- Name: efactura_company_connections; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.efactura_company_connections (
    id integer NOT NULL,
    cif character varying(20) NOT NULL,
    display_name character varying(255) NOT NULL,
    environment character varying(20) DEFAULT 'test'::character varying NOT NULL,
    last_sync_at timestamp without time zone,
    last_received_cursor character varying(100),
    last_sent_cursor character varying(100),
    status character varying(20) DEFAULT 'active'::character varying NOT NULL,
    status_message text,
    config jsonb DEFAULT '{}'::jsonb,
    cert_fingerprint character varying(64),
    cert_expires_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.efactura_company_connections OWNER TO doadmin;

--
-- Name: efactura_company_connections_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.efactura_company_connections_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.efactura_company_connections_id_seq OWNER TO doadmin;

--
-- Name: efactura_company_connections_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.efactura_company_connections_id_seq OWNED BY public.efactura_company_connections.id;


--
-- Name: efactura_invoice_artifacts; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.efactura_invoice_artifacts (
    id integer NOT NULL,
    invoice_id integer NOT NULL,
    artifact_type character varying(20) NOT NULL,
    storage_uri text NOT NULL,
    original_filename character varying(255),
    mime_type character varying(100),
    checksum character varying(64),
    size_bytes integer DEFAULT 0,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.efactura_invoice_artifacts OWNER TO doadmin;

--
-- Name: efactura_invoice_artifacts_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.efactura_invoice_artifacts_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.efactura_invoice_artifacts_id_seq OWNER TO doadmin;

--
-- Name: efactura_invoice_artifacts_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.efactura_invoice_artifacts_id_seq OWNED BY public.efactura_invoice_artifacts.id;


--
-- Name: efactura_invoice_refs; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.efactura_invoice_refs (
    id integer NOT NULL,
    invoice_id integer NOT NULL,
    external_system character varying(20) DEFAULT 'anaf'::character varying NOT NULL,
    message_id character varying(100) NOT NULL,
    upload_id character varying(100),
    download_id character varying(100),
    xml_hash character varying(64),
    signature_hash character varying(64),
    raw_response_hash character varying(64),
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.efactura_invoice_refs OWNER TO doadmin;

--
-- Name: efactura_invoice_refs_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.efactura_invoice_refs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.efactura_invoice_refs_id_seq OWNER TO doadmin;

--
-- Name: efactura_invoice_refs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.efactura_invoice_refs_id_seq OWNED BY public.efactura_invoice_refs.id;


--
-- Name: efactura_invoices; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.efactura_invoices (
    id integer NOT NULL,
    cif_owner character varying(20) NOT NULL,
    direction character varying(20) NOT NULL,
    partner_cif character varying(20) NOT NULL,
    partner_name character varying(500),
    invoice_number character varying(100) NOT NULL,
    invoice_series character varying(50),
    issue_date date,
    due_date date,
    total_amount numeric(15,2) DEFAULT 0 NOT NULL,
    total_vat numeric(15,2) DEFAULT 0 NOT NULL,
    total_without_vat numeric(15,2) DEFAULT 0 NOT NULL,
    currency character varying(3) DEFAULT 'RON'::character varying NOT NULL,
    status character varying(20) DEFAULT 'processed'::character varying NOT NULL,
    company_id integer,
    jarvis_invoice_id integer,
    xml_content text,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    ignored boolean DEFAULT false NOT NULL,
    deleted_at timestamp without time zone,
    type_override character varying(100),
    department_override character varying(255),
    subdepartment_override character varying(255),
    department_override_2 character varying(255),
    subdepartment_override_2 character varying(255)
);


ALTER TABLE public.efactura_invoices OWNER TO doadmin;

--
-- Name: efactura_invoices_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.efactura_invoices_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.efactura_invoices_id_seq OWNER TO doadmin;

--
-- Name: efactura_invoices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.efactura_invoices_id_seq OWNED BY public.efactura_invoices.id;


--
-- Name: efactura_oauth_tokens; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.efactura_oauth_tokens (
    id integer NOT NULL,
    cif character varying(20) NOT NULL,
    access_token text NOT NULL,
    refresh_token text,
    token_type character varying(20) DEFAULT 'Bearer'::character varying,
    expires_at timestamp without time zone,
    scope character varying(100),
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.efactura_oauth_tokens OWNER TO doadmin;

--
-- Name: efactura_oauth_tokens_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.efactura_oauth_tokens_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.efactura_oauth_tokens_id_seq OWNER TO doadmin;

--
-- Name: efactura_oauth_tokens_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.efactura_oauth_tokens_id_seq OWNED BY public.efactura_oauth_tokens.id;


--
-- Name: efactura_supplier_types; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.efactura_supplier_types (
    id integer CONSTRAINT efactura_partner_types_id_not_null NOT NULL,
    name character varying(100) CONSTRAINT efactura_partner_types_name_not_null NOT NULL,
    description text,
    is_active boolean DEFAULT true CONSTRAINT efactura_partner_types_is_active_not_null NOT NULL,
    created_at timestamp without time zone DEFAULT now() CONSTRAINT efactura_partner_types_created_at_not_null NOT NULL,
    updated_at timestamp without time zone DEFAULT now() CONSTRAINT efactura_partner_types_updated_at_not_null NOT NULL,
    hide_in_filter boolean DEFAULT true CONSTRAINT efactura_partner_types_hide_in_filter_not_null NOT NULL
);


ALTER TABLE public.efactura_supplier_types OWNER TO doadmin;

--
-- Name: efactura_partner_types_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.efactura_partner_types_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.efactura_partner_types_id_seq OWNER TO doadmin;

--
-- Name: efactura_partner_types_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.efactura_partner_types_id_seq OWNED BY public.efactura_supplier_types.id;


--
-- Name: efactura_supplier_mapping_types; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.efactura_supplier_mapping_types (
    mapping_id integer NOT NULL,
    type_id integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.efactura_supplier_mapping_types OWNER TO doadmin;

--
-- Name: efactura_supplier_mappings; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.efactura_supplier_mappings (
    id integer NOT NULL,
    partner_name character varying(255) NOT NULL,
    partner_cif character varying(50),
    supplier_name character varying(255) NOT NULL,
    supplier_note text,
    supplier_vat character varying(50),
    kod_konto character varying(50),
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL,
    type_id integer,
    department character varying(255),
    subdepartment character varying(255),
    brand character varying(255)
);


ALTER TABLE public.efactura_supplier_mappings OWNER TO doadmin;

--
-- Name: efactura_supplier_mappings_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.efactura_supplier_mappings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.efactura_supplier_mappings_id_seq OWNER TO doadmin;

--
-- Name: efactura_supplier_mappings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.efactura_supplier_mappings_id_seq OWNED BY public.efactura_supplier_mappings.id;


--
-- Name: efactura_sync_errors; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.efactura_sync_errors (
    id integer NOT NULL,
    run_id character varying(36) NOT NULL,
    message_id character varying(100),
    invoice_ref character varying(100),
    error_type character varying(20) NOT NULL,
    error_code character varying(50),
    error_message text NOT NULL,
    request_hash character varying(64),
    response_hash character varying(64),
    stack_trace text,
    is_retryable boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.efactura_sync_errors OWNER TO doadmin;

--
-- Name: efactura_sync_errors_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.efactura_sync_errors_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.efactura_sync_errors_id_seq OWNER TO doadmin;

--
-- Name: efactura_sync_errors_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.efactura_sync_errors_id_seq OWNED BY public.efactura_sync_errors.id;


--
-- Name: efactura_sync_runs; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.efactura_sync_runs (
    id integer NOT NULL,
    run_id character varying(36) NOT NULL,
    company_cif character varying(20) NOT NULL,
    started_at timestamp without time zone DEFAULT now() NOT NULL,
    finished_at timestamp without time zone,
    success boolean DEFAULT false,
    direction character varying(20),
    messages_checked integer DEFAULT 0,
    invoices_fetched integer DEFAULT 0,
    invoices_created integer DEFAULT 0,
    invoices_updated integer DEFAULT 0,
    invoices_skipped integer DEFAULT 0,
    errors_count integer DEFAULT 0,
    cursor_before character varying(100),
    cursor_after character varying(100),
    error_summary text
);


ALTER TABLE public.efactura_sync_runs OWNER TO doadmin;

--
-- Name: efactura_sync_runs_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.efactura_sync_runs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.efactura_sync_runs_id_seq OWNER TO doadmin;

--
-- Name: efactura_sync_runs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.efactura_sync_runs_id_seq OWNED BY public.efactura_sync_runs.id;


--
-- Name: entity_tags; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.entity_tags (
    id integer NOT NULL,
    tag_id integer NOT NULL,
    entity_type character varying(30) NOT NULL,
    entity_id integer NOT NULL,
    tagged_by integer NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.entity_tags OWNER TO doadmin;

--
-- Name: entity_tags_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.entity_tags_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.entity_tags_id_seq OWNER TO doadmin;

--
-- Name: entity_tags_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.entity_tags_id_seq OWNED BY public.entity_tags.id;


--
-- Name: invoice_templates; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.invoice_templates (
    id integer NOT NULL,
    name text NOT NULL,
    template_type text DEFAULT 'fixed'::text,
    supplier text,
    supplier_vat text,
    customer_vat text,
    currency text DEFAULT 'RON'::text,
    description text,
    invoice_number_regex text,
    invoice_date_regex text,
    invoice_value_regex text,
    date_format text DEFAULT '%Y-%m-%d'::text,
    supplier_regex text,
    supplier_vat_regex text,
    customer_vat_regex text,
    currency_regex text,
    sample_invoice_path text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.invoice_templates OWNER TO doadmin;

--
-- Name: invoice_templates_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.invoice_templates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.invoice_templates_id_seq OWNER TO doadmin;

--
-- Name: invoice_templates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.invoice_templates_id_seq OWNED BY public.invoice_templates.id;


--
-- Name: invoices; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.invoices (
    id integer NOT NULL,
    supplier text NOT NULL,
    invoice_template text,
    invoice_number text NOT NULL,
    invoice_date date NOT NULL,
    invoice_value numeric(15,2) NOT NULL,
    currency text DEFAULT 'RON'::text,
    drive_link text,
    comment text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    value_ron numeric(15,2),
    value_eur numeric(15,2),
    exchange_rate numeric(10,6),
    deleted_at timestamp without time zone,
    status text DEFAULT 'new'::text,
    payment_status text DEFAULT 'not_paid'::text,
    vat_rate numeric(5,2),
    subtract_vat boolean DEFAULT false,
    net_value numeric(15,2)
);


ALTER TABLE public.invoices OWNER TO doadmin;

--
-- Name: invoices_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.invoices_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.invoices_id_seq OWNER TO doadmin;

--
-- Name: invoices_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.invoices_id_seq OWNED BY public.invoices.id;


--
-- Name: module_menu_items; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.module_menu_items (
    id integer NOT NULL,
    parent_id integer,
    module_key text NOT NULL,
    name text NOT NULL,
    description text,
    icon text DEFAULT 'bi-grid'::text,
    url text,
    color text DEFAULT '#6c757d'::text,
    status text DEFAULT 'active'::text,
    sort_order integer DEFAULT 0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT module_menu_items_status_check CHECK ((status = ANY (ARRAY['active'::text, 'coming_soon'::text, 'hidden'::text])))
);


ALTER TABLE public.module_menu_items OWNER TO doadmin;

--
-- Name: module_menu_items_id_seq1; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.module_menu_items_id_seq1
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.module_menu_items_id_seq1 OWNER TO doadmin;

--
-- Name: module_menu_items_id_seq1; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.module_menu_items_id_seq1 OWNED BY public.module_menu_items.id;


--
-- Name: notification_log; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.notification_log (
    id integer NOT NULL,
    responsable_id integer,
    invoice_id integer,
    notification_type text NOT NULL,
    subject text,
    message text,
    status text DEFAULT 'pending'::text,
    error_message text,
    sent_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.notification_log OWNER TO doadmin;

--
-- Name: notification_log_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.notification_log_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.notification_log_id_seq OWNER TO doadmin;

--
-- Name: notification_log_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.notification_log_id_seq OWNED BY public.notification_log.id;


--
-- Name: notification_settings; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.notification_settings (
    id integer NOT NULL,
    setting_key text NOT NULL,
    setting_value text,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.notification_settings OWNER TO doadmin;

--
-- Name: notification_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.notification_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.notification_settings_id_seq OWNER TO doadmin;

--
-- Name: notification_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.notification_settings_id_seq OWNED BY public.notification_settings.id;


--
-- Name: notifications; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.notifications (
    id integer NOT NULL,
    user_id integer NOT NULL,
    type text DEFAULT 'info'::text NOT NULL,
    title text NOT NULL,
    message text,
    link text,
    entity_type text,
    entity_id integer,
    is_read boolean DEFAULT false,
    created_at timestamp with time zone DEFAULT now()
);


ALTER TABLE public.notifications OWNER TO doadmin;

--
-- Name: notifications_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.notifications_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.notifications_id_seq OWNER TO doadmin;

--
-- Name: notifications_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.notifications_id_seq OWNED BY public.notifications.id;


--
-- Name: password_reset_tokens; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.password_reset_tokens (
    id integer NOT NULL,
    user_id integer,
    token text NOT NULL,
    expires_at timestamp without time zone NOT NULL,
    used_at timestamp without time zone,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.password_reset_tokens OWNER TO doadmin;

--
-- Name: password_reset_tokens_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.password_reset_tokens_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.password_reset_tokens_id_seq OWNER TO doadmin;

--
-- Name: password_reset_tokens_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.password_reset_tokens_id_seq OWNED BY public.password_reset_tokens.id;


--
-- Name: performance_reports; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.performance_reports (
    id integer NOT NULL,
    endpoint text NOT NULL,
    method text NOT NULL,
    duration_ms real NOT NULL,
    status_code integer,
    user_id integer,
    query_params text,
    request_size integer,
    response_size integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.performance_reports OWNER TO doadmin;

--
-- Name: performance_reports_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.performance_reports_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.performance_reports_id_seq OWNER TO doadmin;

--
-- Name: performance_reports_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.performance_reports_id_seq OWNED BY public.performance_reports.id;


--
-- Name: permissions; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.permissions (
    id integer NOT NULL,
    module_key text NOT NULL,
    permission_key text NOT NULL,
    label text NOT NULL,
    description text,
    icon text,
    sort_order integer DEFAULT 0,
    parent_id integer,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.permissions OWNER TO doadmin;

--
-- Name: permissions_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.permissions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.permissions_id_seq OWNER TO doadmin;

--
-- Name: permissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.permissions_id_seq OWNED BY public.permissions.id;


--
-- Name: permissions_v2; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.permissions_v2 (
    id integer NOT NULL,
    module_key text NOT NULL,
    module_label text NOT NULL,
    module_icon text,
    entity_key text NOT NULL,
    entity_label text NOT NULL,
    action_key text NOT NULL,
    action_label text NOT NULL,
    description text,
    is_scope_based boolean DEFAULT true,
    sort_order integer DEFAULT 0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.permissions_v2 OWNER TO doadmin;

--
-- Name: permissions_v2_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.permissions_v2_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.permissions_v2_id_seq OWNER TO doadmin;

--
-- Name: permissions_v2_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.permissions_v2_id_seq OWNED BY public.permissions_v2.id;


--
-- Name: reinvoice_destinations; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.reinvoice_destinations (
    id integer NOT NULL,
    allocation_id integer NOT NULL,
    company text NOT NULL,
    brand text,
    department text,
    subdepartment text,
    percentage numeric(7,4) NOT NULL,
    value numeric(15,2),
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.reinvoice_destinations OWNER TO doadmin;

--
-- Name: reinvoice_destinations_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.reinvoice_destinations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.reinvoice_destinations_id_seq OWNER TO doadmin;

--
-- Name: reinvoice_destinations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.reinvoice_destinations_id_seq OWNED BY public.reinvoice_destinations.id;


--
-- Name: role_permissions; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.role_permissions (
    id integer NOT NULL,
    role_id integer NOT NULL,
    permission_id integer NOT NULL,
    granted boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.role_permissions OWNER TO doadmin;

--
-- Name: role_permissions_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.role_permissions_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.role_permissions_id_seq OWNER TO doadmin;

--
-- Name: role_permissions_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.role_permissions_id_seq OWNED BY public.role_permissions.id;


--
-- Name: role_permissions_v2; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.role_permissions_v2 (
    id integer NOT NULL,
    role_id integer NOT NULL,
    permission_id integer NOT NULL,
    scope public.permission_scope DEFAULT 'deny'::public.permission_scope,
    granted boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.role_permissions_v2 OWNER TO doadmin;

--
-- Name: role_permissions_v2_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.role_permissions_v2_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.role_permissions_v2_id_seq OWNER TO doadmin;

--
-- Name: role_permissions_v2_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.role_permissions_v2_id_seq OWNED BY public.role_permissions_v2.id;


--
-- Name: roles; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.roles (
    id integer NOT NULL,
    name text NOT NULL,
    description text,
    can_add_invoices boolean DEFAULT false,
    can_delete_invoices boolean DEFAULT false,
    can_view_invoices boolean DEFAULT false,
    can_access_accounting boolean DEFAULT false,
    can_access_settings boolean DEFAULT false,
    can_access_connectors boolean DEFAULT false,
    can_access_templates boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    can_edit_invoices boolean DEFAULT false,
    can_access_hr boolean DEFAULT false,
    is_hr_manager boolean DEFAULT false,
    can_access_efactura boolean DEFAULT false,
    can_access_statements boolean DEFAULT false
);


ALTER TABLE public.roles OWNER TO doadmin;

--
-- Name: roles_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.roles_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.roles_id_seq OWNER TO doadmin;

--
-- Name: roles_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.roles_id_seq OWNED BY public.roles.id;


--
-- Name: subdepartments; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.subdepartments (
    id integer NOT NULL,
    name text NOT NULL,
    is_active boolean DEFAULT true
);


ALTER TABLE public.subdepartments OWNER TO doadmin;

--
-- Name: subdepartments_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.subdepartments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.subdepartments_id_seq OWNER TO doadmin;

--
-- Name: subdepartments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.subdepartments_id_seq OWNED BY public.subdepartments.id;


--
-- Name: tag_groups; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.tag_groups (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    description text,
    color character varying(7) DEFAULT '#6c757d'::character varying,
    sort_order integer DEFAULT 0,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.tag_groups OWNER TO doadmin;

--
-- Name: tag_groups_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.tag_groups_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.tag_groups_id_seq OWNER TO doadmin;

--
-- Name: tag_groups_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.tag_groups_id_seq OWNED BY public.tag_groups.id;


--
-- Name: tags; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.tags (
    id integer NOT NULL,
    name character varying(100) NOT NULL,
    group_id integer,
    color character varying(7) DEFAULT '#0d6efd'::character varying,
    icon character varying(50),
    is_global boolean DEFAULT false NOT NULL,
    created_by integer,
    sort_order integer DEFAULT 0,
    is_active boolean DEFAULT true NOT NULL,
    created_at timestamp without time zone DEFAULT now() NOT NULL,
    updated_at timestamp without time zone DEFAULT now() NOT NULL
);


ALTER TABLE public.tags OWNER TO doadmin;

--
-- Name: tags_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.tags_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.tags_id_seq OWNER TO doadmin;

--
-- Name: tags_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.tags_id_seq OWNED BY public.tags.id;


--
-- Name: theme_settings; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.theme_settings (
    id integer NOT NULL,
    theme_name text DEFAULT 'default'::text NOT NULL,
    is_active boolean DEFAULT true,
    settings jsonb DEFAULT '{}'::jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.theme_settings OWNER TO doadmin;

--
-- Name: theme_settings_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.theme_settings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.theme_settings_id_seq OWNER TO doadmin;

--
-- Name: theme_settings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.theme_settings_id_seq OWNED BY public.theme_settings.id;


--
-- Name: user_events; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.user_events (
    id integer NOT NULL,
    user_id integer,
    user_email text,
    event_type text NOT NULL,
    event_description text,
    entity_type text,
    entity_id integer,
    ip_address text,
    user_agent text,
    details jsonb DEFAULT '{}'::jsonb,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.user_events OWNER TO doadmin;

--
-- Name: user_events_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.user_events_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_events_id_seq OWNER TO doadmin;

--
-- Name: user_events_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.user_events_id_seq OWNED BY public.user_events.id;


--
-- Name: user_filter_presets; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.user_filter_presets (
    id integer NOT NULL,
    user_id integer NOT NULL,
    page_key character varying(50) NOT NULL,
    name character varying(100) NOT NULL,
    is_default boolean DEFAULT false,
    preset_data jsonb DEFAULT '{}'::jsonb NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.user_filter_presets OWNER TO doadmin;

--
-- Name: user_filter_presets_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.user_filter_presets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.user_filter_presets_id_seq OWNER TO doadmin;

--
-- Name: user_filter_presets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.user_filter_presets_id_seq OWNED BY public.user_filter_presets.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.users (
    id integer NOT NULL,
    name text NOT NULL,
    email text NOT NULL,
    phone text,
    is_active boolean DEFAULT true,
    can_add_invoices boolean DEFAULT true,
    can_delete_invoices boolean DEFAULT false,
    can_view_invoices boolean DEFAULT true,
    can_access_accounting boolean DEFAULT true,
    can_access_settings boolean DEFAULT false,
    can_access_connectors boolean DEFAULT false,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    role_id integer,
    password_hash text,
    last_login timestamp without time zone,
    last_seen timestamp without time zone,
    company text,
    brand text,
    department text,
    subdepartment text,
    org_unit_id integer,
    notify_on_allocation boolean DEFAULT true,
    migrated_from text,
    migrated_at timestamp without time zone
);


ALTER TABLE public.users OWNER TO doadmin;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO doadmin;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: vat_rates; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.vat_rates (
    id integer NOT NULL,
    name text NOT NULL,
    rate numeric(5,2) NOT NULL,
    is_default boolean DEFAULT false,
    is_active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.vat_rates OWNER TO doadmin;

--
-- Name: vat_rates_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.vat_rates_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.vat_rates_id_seq OWNER TO doadmin;

--
-- Name: vat_rates_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.vat_rates_id_seq OWNED BY public.vat_rates.id;


--
-- Name: vendor_mappings; Type: TABLE; Schema: public; Owner: doadmin
--

CREATE TABLE public.vendor_mappings (
    id integer NOT NULL,
    pattern text NOT NULL,
    supplier_name text NOT NULL,
    supplier_vat text,
    template_id integer,
    is_active boolean DEFAULT true,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);


ALTER TABLE public.vendor_mappings OWNER TO doadmin;

--
-- Name: vendor_mappings_id_seq; Type: SEQUENCE; Schema: public; Owner: doadmin
--

CREATE SEQUENCE public.vendor_mappings_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.vendor_mappings_id_seq OWNER TO doadmin;

--
-- Name: vendor_mappings_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: doadmin
--

ALTER SEQUENCE public.vendor_mappings_id_seq OWNED BY public.vendor_mappings.id;


--
-- Name: conversation_contexts id; Type: DEFAULT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.conversation_contexts ALTER COLUMN id SET DEFAULT nextval('ai_agent.conversation_contexts_id_seq'::regclass);


--
-- Name: conversation_logs id; Type: DEFAULT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.conversation_logs ALTER COLUMN id SET DEFAULT nextval('ai_agent.conversation_logs_id_seq'::regclass);


--
-- Name: conversations id; Type: DEFAULT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.conversations ALTER COLUMN id SET DEFAULT nextval('ai_agent.conversations_id_seq'::regclass);


--
-- Name: messages id; Type: DEFAULT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.messages ALTER COLUMN id SET DEFAULT nextval('ai_agent.messages_id_seq'::regclass);


--
-- Name: model_configs id; Type: DEFAULT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.model_configs ALTER COLUMN id SET DEFAULT nextval('ai_agent.model_configs_id_seq'::regclass);


--
-- Name: rag_documents id; Type: DEFAULT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.rag_documents ALTER COLUMN id SET DEFAULT nextval('ai_agent.rag_documents_id_seq'::regclass);


--
-- Name: bonus_types id; Type: DEFAULT; Schema: hr; Owner: doadmin
--

ALTER TABLE ONLY hr.bonus_types ALTER COLUMN id SET DEFAULT nextval('hr.bonus_types_id_seq'::regclass);


--
-- Name: event_bonuses id; Type: DEFAULT; Schema: hr; Owner: doadmin
--

ALTER TABLE ONLY hr.event_bonuses ALTER COLUMN id SET DEFAULT nextval('hr.event_bonuses_id_seq'::regclass);


--
-- Name: events id; Type: DEFAULT; Schema: hr; Owner: doadmin
--

ALTER TABLE ONLY hr.events ALTER COLUMN id SET DEFAULT nextval('hr.events_id_seq'::regclass);


--
-- Name: allocations id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.allocations ALTER COLUMN id SET DEFAULT nextval('public.allocations_id_seq'::regclass);


--
-- Name: approval_audit_log id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_audit_log ALTER COLUMN id SET DEFAULT nextval('public.approval_audit_log_id_seq'::regclass);


--
-- Name: approval_decisions id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_decisions ALTER COLUMN id SET DEFAULT nextval('public.approval_decisions_id_seq'::regclass);


--
-- Name: approval_delegations id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_delegations ALTER COLUMN id SET DEFAULT nextval('public.approval_delegations_id_seq'::regclass);


--
-- Name: approval_flows id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_flows ALTER COLUMN id SET DEFAULT nextval('public.approval_flows_id_seq'::regclass);


--
-- Name: approval_requests id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_requests ALTER COLUMN id SET DEFAULT nextval('public.approval_requests_id_seq'::regclass);


--
-- Name: approval_steps id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_steps ALTER COLUMN id SET DEFAULT nextval('public.approval_steps_id_seq'::regclass);


--
-- Name: auto_tag_rules id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.auto_tag_rules ALTER COLUMN id SET DEFAULT nextval('public.auto_tag_rules_id_seq'::regclass);


--
-- Name: bank_statement_transactions id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.bank_statement_transactions ALTER COLUMN id SET DEFAULT nextval('public.bank_statement_transactions_id_seq'::regclass);


--
-- Name: bank_statements id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.bank_statements ALTER COLUMN id SET DEFAULT nextval('public.bank_statements_id_seq'::regclass);


--
-- Name: brands id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.brands ALTER COLUMN id SET DEFAULT nextval('public.brands_id_seq'::regclass);


--
-- Name: companies id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.companies ALTER COLUMN id SET DEFAULT nextval('public.companies_id_seq'::regclass);


--
-- Name: company_brands id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.company_brands ALTER COLUMN id SET DEFAULT nextval('public.company_brands_id_seq'::regclass);


--
-- Name: connector_sync_log id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.connector_sync_log ALTER COLUMN id SET DEFAULT nextval('public.connector_sync_log_id_seq'::regclass);


--
-- Name: connectors id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.connectors ALTER COLUMN id SET DEFAULT nextval('public.connectors_id_seq'::regclass);


--
-- Name: department_structure id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.department_structure ALTER COLUMN id SET DEFAULT nextval('public.department_structure_id_seq'::regclass);


--
-- Name: departments id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.departments ALTER COLUMN id SET DEFAULT nextval('public.departments_id_seq'::regclass);


--
-- Name: dropdown_options id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.dropdown_options ALTER COLUMN id SET DEFAULT nextval('public.dropdown_options_id_seq'::regclass);


--
-- Name: efactura_company_connections id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_company_connections ALTER COLUMN id SET DEFAULT nextval('public.efactura_company_connections_id_seq'::regclass);


--
-- Name: efactura_invoice_artifacts id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_invoice_artifacts ALTER COLUMN id SET DEFAULT nextval('public.efactura_invoice_artifacts_id_seq'::regclass);


--
-- Name: efactura_invoice_refs id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_invoice_refs ALTER COLUMN id SET DEFAULT nextval('public.efactura_invoice_refs_id_seq'::regclass);


--
-- Name: efactura_invoices id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_invoices ALTER COLUMN id SET DEFAULT nextval('public.efactura_invoices_id_seq'::regclass);


--
-- Name: efactura_oauth_tokens id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_oauth_tokens ALTER COLUMN id SET DEFAULT nextval('public.efactura_oauth_tokens_id_seq'::regclass);


--
-- Name: efactura_supplier_mappings id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_supplier_mappings ALTER COLUMN id SET DEFAULT nextval('public.efactura_supplier_mappings_id_seq'::regclass);


--
-- Name: efactura_supplier_types id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_supplier_types ALTER COLUMN id SET DEFAULT nextval('public.efactura_partner_types_id_seq'::regclass);


--
-- Name: efactura_sync_errors id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_sync_errors ALTER COLUMN id SET DEFAULT nextval('public.efactura_sync_errors_id_seq'::regclass);


--
-- Name: efactura_sync_runs id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_sync_runs ALTER COLUMN id SET DEFAULT nextval('public.efactura_sync_runs_id_seq'::regclass);


--
-- Name: entity_tags id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.entity_tags ALTER COLUMN id SET DEFAULT nextval('public.entity_tags_id_seq'::regclass);


--
-- Name: invoice_templates id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.invoice_templates ALTER COLUMN id SET DEFAULT nextval('public.invoice_templates_id_seq'::regclass);


--
-- Name: invoices id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.invoices ALTER COLUMN id SET DEFAULT nextval('public.invoices_id_seq'::regclass);


--
-- Name: module_menu_items id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.module_menu_items ALTER COLUMN id SET DEFAULT nextval('public.module_menu_items_id_seq1'::regclass);


--
-- Name: notification_log id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.notification_log ALTER COLUMN id SET DEFAULT nextval('public.notification_log_id_seq'::regclass);


--
-- Name: notification_settings id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.notification_settings ALTER COLUMN id SET DEFAULT nextval('public.notification_settings_id_seq'::regclass);


--
-- Name: notifications id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.notifications ALTER COLUMN id SET DEFAULT nextval('public.notifications_id_seq'::regclass);


--
-- Name: password_reset_tokens id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.password_reset_tokens ALTER COLUMN id SET DEFAULT nextval('public.password_reset_tokens_id_seq'::regclass);


--
-- Name: performance_reports id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.performance_reports ALTER COLUMN id SET DEFAULT nextval('public.performance_reports_id_seq'::regclass);


--
-- Name: permissions id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.permissions ALTER COLUMN id SET DEFAULT nextval('public.permissions_id_seq'::regclass);


--
-- Name: permissions_v2 id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.permissions_v2 ALTER COLUMN id SET DEFAULT nextval('public.permissions_v2_id_seq'::regclass);


--
-- Name: reinvoice_destinations id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.reinvoice_destinations ALTER COLUMN id SET DEFAULT nextval('public.reinvoice_destinations_id_seq'::regclass);


--
-- Name: role_permissions id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.role_permissions ALTER COLUMN id SET DEFAULT nextval('public.role_permissions_id_seq'::regclass);


--
-- Name: role_permissions_v2 id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.role_permissions_v2 ALTER COLUMN id SET DEFAULT nextval('public.role_permissions_v2_id_seq'::regclass);


--
-- Name: roles id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.roles ALTER COLUMN id SET DEFAULT nextval('public.roles_id_seq'::regclass);


--
-- Name: subdepartments id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.subdepartments ALTER COLUMN id SET DEFAULT nextval('public.subdepartments_id_seq'::regclass);


--
-- Name: tag_groups id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.tag_groups ALTER COLUMN id SET DEFAULT nextval('public.tag_groups_id_seq'::regclass);


--
-- Name: tags id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.tags ALTER COLUMN id SET DEFAULT nextval('public.tags_id_seq'::regclass);


--
-- Name: theme_settings id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.theme_settings ALTER COLUMN id SET DEFAULT nextval('public.theme_settings_id_seq'::regclass);


--
-- Name: user_events id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.user_events ALTER COLUMN id SET DEFAULT nextval('public.user_events_id_seq'::regclass);


--
-- Name: user_filter_presets id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.user_filter_presets ALTER COLUMN id SET DEFAULT nextval('public.user_filter_presets_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: vat_rates id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.vat_rates ALTER COLUMN id SET DEFAULT nextval('public.vat_rates_id_seq'::regclass);


--
-- Name: vendor_mappings id; Type: DEFAULT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.vendor_mappings ALTER COLUMN id SET DEFAULT nextval('public.vendor_mappings_id_seq'::regclass);


--
-- Name: conversation_contexts conversation_contexts_pkey; Type: CONSTRAINT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.conversation_contexts
    ADD CONSTRAINT conversation_contexts_pkey PRIMARY KEY (id);


--
-- Name: conversation_logs conversation_logs_pkey; Type: CONSTRAINT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.conversation_logs
    ADD CONSTRAINT conversation_logs_pkey PRIMARY KEY (id);


--
-- Name: conversations conversations_pkey; Type: CONSTRAINT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.conversations
    ADD CONSTRAINT conversations_pkey PRIMARY KEY (id);


--
-- Name: messages messages_pkey; Type: CONSTRAINT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.messages
    ADD CONSTRAINT messages_pkey PRIMARY KEY (id);


--
-- Name: model_configs model_configs_pkey; Type: CONSTRAINT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.model_configs
    ADD CONSTRAINT model_configs_pkey PRIMARY KEY (id);


--
-- Name: rag_documents rag_documents_pkey; Type: CONSTRAINT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.rag_documents
    ADD CONSTRAINT rag_documents_pkey PRIMARY KEY (id);


--
-- Name: bonus_types bonus_types_pkey; Type: CONSTRAINT; Schema: hr; Owner: doadmin
--

ALTER TABLE ONLY hr.bonus_types
    ADD CONSTRAINT bonus_types_pkey PRIMARY KEY (id);


--
-- Name: event_bonuses event_bonuses_pkey; Type: CONSTRAINT; Schema: hr; Owner: doadmin
--

ALTER TABLE ONLY hr.event_bonuses
    ADD CONSTRAINT event_bonuses_pkey PRIMARY KEY (id);


--
-- Name: events events_pkey; Type: CONSTRAINT; Schema: hr; Owner: doadmin
--

ALTER TABLE ONLY hr.events
    ADD CONSTRAINT events_pkey PRIMARY KEY (id);


--
-- Name: allocations allocations_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.allocations
    ADD CONSTRAINT allocations_pkey PRIMARY KEY (id);


--
-- Name: approval_audit_log approval_audit_log_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_audit_log
    ADD CONSTRAINT approval_audit_log_pkey PRIMARY KEY (id);


--
-- Name: approval_decisions approval_decisions_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_decisions
    ADD CONSTRAINT approval_decisions_pkey PRIMARY KEY (id);


--
-- Name: approval_delegations approval_delegations_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_delegations
    ADD CONSTRAINT approval_delegations_pkey PRIMARY KEY (id);


--
-- Name: approval_flows approval_flows_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_flows
    ADD CONSTRAINT approval_flows_pkey PRIMARY KEY (id);


--
-- Name: approval_flows approval_flows_slug_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_flows
    ADD CONSTRAINT approval_flows_slug_key UNIQUE (slug);


--
-- Name: approval_requests approval_requests_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT approval_requests_pkey PRIMARY KEY (id);


--
-- Name: approval_steps approval_steps_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_steps
    ADD CONSTRAINT approval_steps_pkey PRIMARY KEY (id);


--
-- Name: auto_tag_rules auto_tag_rules_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.auto_tag_rules
    ADD CONSTRAINT auto_tag_rules_pkey PRIMARY KEY (id);


--
-- Name: bank_statement_transactions bank_statement_transactions_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.bank_statement_transactions
    ADD CONSTRAINT bank_statement_transactions_pkey PRIMARY KEY (id);


--
-- Name: bank_statements bank_statements_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.bank_statements
    ADD CONSTRAINT bank_statements_pkey PRIMARY KEY (id);


--
-- Name: brands brands_name_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.brands
    ADD CONSTRAINT brands_name_key UNIQUE (name);


--
-- Name: brands brands_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.brands
    ADD CONSTRAINT brands_pkey PRIMARY KEY (id);


--
-- Name: companies companies_company_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT companies_company_key UNIQUE (company);


--
-- Name: companies companies_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.companies
    ADD CONSTRAINT companies_pkey PRIMARY KEY (id);


--
-- Name: company_brands company_brands_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.company_brands
    ADD CONSTRAINT company_brands_pkey PRIMARY KEY (id);


--
-- Name: connector_sync_log connector_sync_log_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.connector_sync_log
    ADD CONSTRAINT connector_sync_log_pkey PRIMARY KEY (id);


--
-- Name: connectors connectors_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.connectors
    ADD CONSTRAINT connectors_pkey PRIMARY KEY (id);


--
-- Name: department_structure department_structure_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.department_structure
    ADD CONSTRAINT department_structure_pkey PRIMARY KEY (id);


--
-- Name: departments departments_name_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_name_key UNIQUE (name);


--
-- Name: departments departments_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_pkey PRIMARY KEY (id);


--
-- Name: dropdown_options dropdown_options_dropdown_type_value_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.dropdown_options
    ADD CONSTRAINT dropdown_options_dropdown_type_value_key UNIQUE (dropdown_type, value);


--
-- Name: dropdown_options dropdown_options_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.dropdown_options
    ADD CONSTRAINT dropdown_options_pkey PRIMARY KEY (id);


--
-- Name: efactura_company_connections efactura_company_connections_cif_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_company_connections
    ADD CONSTRAINT efactura_company_connections_cif_key UNIQUE (cif);


--
-- Name: efactura_company_connections efactura_company_connections_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_company_connections
    ADD CONSTRAINT efactura_company_connections_pkey PRIMARY KEY (id);


--
-- Name: efactura_invoice_artifacts efactura_invoice_artifacts_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_invoice_artifacts
    ADD CONSTRAINT efactura_invoice_artifacts_pkey PRIMARY KEY (id);


--
-- Name: efactura_invoice_refs efactura_invoice_refs_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_invoice_refs
    ADD CONSTRAINT efactura_invoice_refs_pkey PRIMARY KEY (id);


--
-- Name: efactura_invoices efactura_invoices_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_invoices
    ADD CONSTRAINT efactura_invoices_pkey PRIMARY KEY (id);


--
-- Name: efactura_oauth_tokens efactura_oauth_tokens_cif_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_oauth_tokens
    ADD CONSTRAINT efactura_oauth_tokens_cif_key UNIQUE (cif);


--
-- Name: efactura_oauth_tokens efactura_oauth_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_oauth_tokens
    ADD CONSTRAINT efactura_oauth_tokens_pkey PRIMARY KEY (id);


--
-- Name: efactura_supplier_types efactura_partner_types_name_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_supplier_types
    ADD CONSTRAINT efactura_partner_types_name_key UNIQUE (name);


--
-- Name: efactura_supplier_types efactura_partner_types_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_supplier_types
    ADD CONSTRAINT efactura_partner_types_pkey PRIMARY KEY (id);


--
-- Name: efactura_supplier_mapping_types efactura_supplier_mapping_types_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_supplier_mapping_types
    ADD CONSTRAINT efactura_supplier_mapping_types_pkey PRIMARY KEY (mapping_id, type_id);


--
-- Name: efactura_supplier_mappings efactura_supplier_mappings_partner_name_partner_cif_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_supplier_mappings
    ADD CONSTRAINT efactura_supplier_mappings_partner_name_partner_cif_key UNIQUE (partner_name, partner_cif);


--
-- Name: efactura_supplier_mappings efactura_supplier_mappings_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_supplier_mappings
    ADD CONSTRAINT efactura_supplier_mappings_pkey PRIMARY KEY (id);


--
-- Name: efactura_sync_errors efactura_sync_errors_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_sync_errors
    ADD CONSTRAINT efactura_sync_errors_pkey PRIMARY KEY (id);


--
-- Name: efactura_sync_runs efactura_sync_runs_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_sync_runs
    ADD CONSTRAINT efactura_sync_runs_pkey PRIMARY KEY (id);


--
-- Name: efactura_sync_runs efactura_sync_runs_run_id_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_sync_runs
    ADD CONSTRAINT efactura_sync_runs_run_id_key UNIQUE (run_id);


--
-- Name: entity_tags entity_tags_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.entity_tags
    ADD CONSTRAINT entity_tags_pkey PRIMARY KEY (id);


--
-- Name: entity_tags entity_tags_tag_id_entity_type_entity_id_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.entity_tags
    ADD CONSTRAINT entity_tags_tag_id_entity_type_entity_id_key UNIQUE (tag_id, entity_type, entity_id);


--
-- Name: invoice_templates invoice_templates_name_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.invoice_templates
    ADD CONSTRAINT invoice_templates_name_key UNIQUE (name);


--
-- Name: invoice_templates invoice_templates_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.invoice_templates
    ADD CONSTRAINT invoice_templates_pkey PRIMARY KEY (id);


--
-- Name: invoices invoices_invoice_number_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_invoice_number_key UNIQUE (invoice_number);


--
-- Name: invoices invoices_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.invoices
    ADD CONSTRAINT invoices_pkey PRIMARY KEY (id);


--
-- Name: module_menu_items module_menu_items_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.module_menu_items
    ADD CONSTRAINT module_menu_items_pkey PRIMARY KEY (id);


--
-- Name: notification_log notification_log_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.notification_log
    ADD CONSTRAINT notification_log_pkey PRIMARY KEY (id);


--
-- Name: notification_settings notification_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.notification_settings
    ADD CONSTRAINT notification_settings_pkey PRIMARY KEY (id);


--
-- Name: notification_settings notification_settings_setting_key_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.notification_settings
    ADD CONSTRAINT notification_settings_setting_key_key UNIQUE (setting_key);


--
-- Name: notifications notifications_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_pkey PRIMARY KEY (id);


--
-- Name: password_reset_tokens password_reset_tokens_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_pkey PRIMARY KEY (id);


--
-- Name: password_reset_tokens password_reset_tokens_token_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_token_key UNIQUE (token);


--
-- Name: performance_reports performance_reports_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.performance_reports
    ADD CONSTRAINT performance_reports_pkey PRIMARY KEY (id);


--
-- Name: permissions permissions_module_key_permission_key_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT permissions_module_key_permission_key_key UNIQUE (module_key, permission_key);


--
-- Name: permissions permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT permissions_pkey PRIMARY KEY (id);


--
-- Name: permissions_v2 permissions_v2_module_key_entity_key_action_key_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.permissions_v2
    ADD CONSTRAINT permissions_v2_module_key_entity_key_action_key_key UNIQUE (module_key, entity_key, action_key);


--
-- Name: permissions_v2 permissions_v2_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.permissions_v2
    ADD CONSTRAINT permissions_v2_pkey PRIMARY KEY (id);


--
-- Name: reinvoice_destinations reinvoice_destinations_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.reinvoice_destinations
    ADD CONSTRAINT reinvoice_destinations_pkey PRIMARY KEY (id);


--
-- Name: role_permissions role_permissions_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_pkey PRIMARY KEY (id);


--
-- Name: role_permissions role_permissions_role_id_permission_id_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_role_id_permission_id_key UNIQUE (role_id, permission_id);


--
-- Name: role_permissions_v2 role_permissions_v2_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.role_permissions_v2
    ADD CONSTRAINT role_permissions_v2_pkey PRIMARY KEY (id);


--
-- Name: role_permissions_v2 role_permissions_v2_role_id_permission_id_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.role_permissions_v2
    ADD CONSTRAINT role_permissions_v2_role_id_permission_id_key UNIQUE (role_id, permission_id);


--
-- Name: roles roles_name_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_name_key UNIQUE (name);


--
-- Name: roles roles_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.roles
    ADD CONSTRAINT roles_pkey PRIMARY KEY (id);


--
-- Name: subdepartments subdepartments_name_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.subdepartments
    ADD CONSTRAINT subdepartments_name_key UNIQUE (name);


--
-- Name: subdepartments subdepartments_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.subdepartments
    ADD CONSTRAINT subdepartments_pkey PRIMARY KEY (id);


--
-- Name: tag_groups tag_groups_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.tag_groups
    ADD CONSTRAINT tag_groups_pkey PRIMARY KEY (id);


--
-- Name: tags tags_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_pkey PRIMARY KEY (id);


--
-- Name: theme_settings theme_settings_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.theme_settings
    ADD CONSTRAINT theme_settings_pkey PRIMARY KEY (id);


--
-- Name: user_events user_events_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.user_events
    ADD CONSTRAINT user_events_pkey PRIMARY KEY (id);


--
-- Name: user_filter_presets user_filter_presets_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.user_filter_presets
    ADD CONSTRAINT user_filter_presets_pkey PRIMARY KEY (id);


--
-- Name: users users_email_key; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_email_key UNIQUE (email);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: vat_rates vat_rates_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.vat_rates
    ADD CONSTRAINT vat_rates_pkey PRIMARY KEY (id);


--
-- Name: vendor_mappings vendor_mappings_pkey; Type: CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.vendor_mappings
    ADD CONSTRAINT vendor_mappings_pkey PRIMARY KEY (id);


--
-- Name: idx_contexts_message; Type: INDEX; Schema: ai_agent; Owner: doadmin
--

CREATE INDEX idx_contexts_message ON ai_agent.conversation_contexts USING btree (message_id);


--
-- Name: idx_conversation_logs_conv; Type: INDEX; Schema: ai_agent; Owner: doadmin
--

CREATE INDEX idx_conversation_logs_conv ON ai_agent.conversation_logs USING btree (conversation_id);


--
-- Name: idx_conversation_logs_created; Type: INDEX; Schema: ai_agent; Owner: doadmin
--

CREATE INDEX idx_conversation_logs_created ON ai_agent.conversation_logs USING btree (created_at);


--
-- Name: idx_conversation_logs_user; Type: INDEX; Schema: ai_agent; Owner: doadmin
--

CREATE INDEX idx_conversation_logs_user ON ai_agent.conversation_logs USING btree (user_id);


--
-- Name: idx_conversations_created; Type: INDEX; Schema: ai_agent; Owner: doadmin
--

CREATE INDEX idx_conversations_created ON ai_agent.conversations USING btree (created_at DESC);


--
-- Name: idx_conversations_status; Type: INDEX; Schema: ai_agent; Owner: doadmin
--

CREATE INDEX idx_conversations_status ON ai_agent.conversations USING btree (status);


--
-- Name: idx_conversations_user; Type: INDEX; Schema: ai_agent; Owner: doadmin
--

CREATE INDEX idx_conversations_user ON ai_agent.conversations USING btree (user_id);


--
-- Name: idx_messages_conversation; Type: INDEX; Schema: ai_agent; Owner: doadmin
--

CREATE INDEX idx_messages_conversation ON ai_agent.messages USING btree (conversation_id);


--
-- Name: idx_messages_created; Type: INDEX; Schema: ai_agent; Owner: doadmin
--

CREATE INDEX idx_messages_created ON ai_agent.messages USING btree (created_at);


--
-- Name: idx_model_configs_default; Type: INDEX; Schema: ai_agent; Owner: doadmin
--

CREATE UNIQUE INDEX idx_model_configs_default ON ai_agent.model_configs USING btree (provider) WHERE (is_default = true);


--
-- Name: idx_rag_documents_active; Type: INDEX; Schema: ai_agent; Owner: doadmin
--

CREATE INDEX idx_rag_documents_active ON ai_agent.rag_documents USING btree (is_active) WHERE (is_active = true);


--
-- Name: idx_rag_documents_company; Type: INDEX; Schema: ai_agent; Owner: doadmin
--

CREATE INDEX idx_rag_documents_company ON ai_agent.rag_documents USING btree (company_id);


--
-- Name: idx_rag_documents_content_fts; Type: INDEX; Schema: ai_agent; Owner: doadmin
--

CREATE INDEX idx_rag_documents_content_fts ON ai_agent.rag_documents USING gin (to_tsvector('english'::regconfig, content));


--
-- Name: idx_rag_documents_embedding; Type: INDEX; Schema: ai_agent; Owner: doadmin
--

CREATE INDEX idx_rag_documents_embedding ON ai_agent.rag_documents USING ivfflat (embedding public.vector_cosine_ops) WITH (lists='100');


--
-- Name: idx_rag_documents_source; Type: INDEX; Schema: ai_agent; Owner: doadmin
--

CREATE INDEX idx_rag_documents_source ON ai_agent.rag_documents USING btree (source_type, source_id);


--
-- Name: idx_hr_bonuses_employee; Type: INDEX; Schema: hr; Owner: doadmin
--

CREATE INDEX idx_hr_bonuses_employee ON hr.event_bonuses USING btree (user_id);


--
-- Name: idx_hr_bonuses_event; Type: INDEX; Schema: hr; Owner: doadmin
--

CREATE INDEX idx_hr_bonuses_event ON hr.event_bonuses USING btree (event_id);


--
-- Name: idx_hr_bonuses_year_month; Type: INDEX; Schema: hr; Owner: doadmin
--

CREATE INDEX idx_hr_bonuses_year_month ON hr.event_bonuses USING btree (year, month);


--
-- Name: idx_hr_events_dates; Type: INDEX; Schema: hr; Owner: doadmin
--

CREATE INDEX idx_hr_events_dates ON hr.events USING btree (start_date, end_date);


--
-- Name: idx_allocations_brand; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_allocations_brand ON public.allocations USING btree (brand);


--
-- Name: idx_allocations_company; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_allocations_company ON public.allocations USING btree (company);


--
-- Name: idx_allocations_department; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_allocations_department ON public.allocations USING btree (department);


--
-- Name: idx_allocations_invoice_company; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_allocations_invoice_company ON public.allocations USING btree (invoice_id, company);


--
-- Name: idx_allocations_invoice_id; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_allocations_invoice_id ON public.allocations USING btree (invoice_id);


--
-- Name: idx_allocations_responsible_user_id; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_allocations_responsible_user_id ON public.allocations USING btree (responsible_user_id);


--
-- Name: idx_approval_audit_request; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_approval_audit_request ON public.approval_audit_log USING btree (request_id);


--
-- Name: idx_approval_audit_timestamp; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_approval_audit_timestamp ON public.approval_audit_log USING btree (created_at);


--
-- Name: idx_approval_decisions_request; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_approval_decisions_request ON public.approval_decisions USING btree (request_id);


--
-- Name: idx_approval_decisions_step; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_approval_decisions_step ON public.approval_decisions USING btree (step_id);


--
-- Name: idx_approval_delegations_active; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_approval_delegations_active ON public.approval_delegations USING btree (is_active, starts_at, ends_at);


--
-- Name: idx_approval_delegations_delegate; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_approval_delegations_delegate ON public.approval_delegations USING btree (delegate_id);


--
-- Name: idx_approval_flows_active; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_approval_flows_active ON public.approval_flows USING btree (is_active);


--
-- Name: idx_approval_flows_entity_type; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_approval_flows_entity_type ON public.approval_flows USING btree (entity_type);


--
-- Name: idx_approval_requests_entity; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_approval_requests_entity ON public.approval_requests USING btree (entity_type, entity_id);


--
-- Name: idx_approval_requests_requested_by; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_approval_requests_requested_by ON public.approval_requests USING btree (requested_by);


--
-- Name: idx_approval_requests_status; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_approval_requests_status ON public.approval_requests USING btree (status);


--
-- Name: idx_approval_requests_step_status; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_approval_requests_step_status ON public.approval_requests USING btree (current_step_id, status);


--
-- Name: idx_approval_steps_flow; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_approval_steps_flow ON public.approval_steps USING btree (flow_id);


--
-- Name: idx_auto_tag_rules_entity_type; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_auto_tag_rules_entity_type ON public.auto_tag_rules USING btree (entity_type) WHERE (is_active = true);


--
-- Name: idx_auto_tag_rules_tag; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_auto_tag_rules_tag ON public.auto_tag_rules USING btree (tag_id);


--
-- Name: idx_bst_invoice_id; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_bst_invoice_id ON public.bank_statement_transactions USING btree (invoice_id);


--
-- Name: idx_dept_structure_company; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_dept_structure_company ON public.department_structure USING btree (company);


--
-- Name: idx_dept_structure_dept; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_dept_structure_dept ON public.department_structure USING btree (department);


--
-- Name: idx_efactura_connections_status; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_connections_status ON public.efactura_company_connections USING btree (status);


--
-- Name: idx_efactura_invoices_date; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_invoices_date ON public.efactura_invoices USING btree (issue_date);


--
-- Name: idx_efactura_invoices_deleted_at; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_invoices_deleted_at ON public.efactura_invoices USING btree (deleted_at);


--
-- Name: idx_efactura_invoices_ignored; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_invoices_ignored ON public.efactura_invoices USING btree (ignored);


--
-- Name: idx_efactura_invoices_invoice_number_trgm; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_invoices_invoice_number_trgm ON public.efactura_invoices USING gin (invoice_number public.gin_trgm_ops);


--
-- Name: idx_efactura_invoices_jarvis; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_invoices_jarvis ON public.efactura_invoices USING btree (jarvis_invoice_id);


--
-- Name: idx_efactura_invoices_owner; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_invoices_owner ON public.efactura_invoices USING btree (cif_owner, direction);


--
-- Name: idx_efactura_invoices_partner_cif_trgm; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_invoices_partner_cif_trgm ON public.efactura_invoices USING gin (partner_cif public.gin_trgm_ops);


--
-- Name: idx_efactura_invoices_partner_name_lower; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_invoices_partner_name_lower ON public.efactura_invoices USING btree (lower((partner_name)::text));


--
-- Name: idx_efactura_invoices_partner_name_trgm; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_invoices_partner_name_trgm ON public.efactura_invoices USING gin (partner_name public.gin_trgm_ops);


--
-- Name: idx_efactura_invoices_status; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_invoices_status ON public.efactura_invoices USING btree (status);


--
-- Name: idx_efactura_mappings_partner_cif_trgm; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_mappings_partner_cif_trgm ON public.efactura_supplier_mappings USING gin (partner_cif public.gin_trgm_ops);


--
-- Name: idx_efactura_mappings_partner_name_lower; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_mappings_partner_name_lower ON public.efactura_supplier_mappings USING btree (lower((partner_name)::text));


--
-- Name: idx_efactura_mappings_partner_name_trgm; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_mappings_partner_name_trgm ON public.efactura_supplier_mappings USING gin (partner_name public.gin_trgm_ops);


--
-- Name: idx_efactura_mappings_supplier_name_trgm; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_mappings_supplier_name_trgm ON public.efactura_supplier_mappings USING gin (supplier_name public.gin_trgm_ops);


--
-- Name: idx_efactura_oauth_cif; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_oauth_cif ON public.efactura_oauth_tokens USING btree (cif);


--
-- Name: idx_efactura_refs_message; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_refs_message ON public.efactura_invoice_refs USING btree (message_id);


--
-- Name: idx_efactura_supplier_mappings_cif; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_supplier_mappings_cif ON public.efactura_supplier_mappings USING btree (partner_cif);


--
-- Name: idx_efactura_supplier_mappings_partner; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_supplier_mappings_partner ON public.efactura_supplier_mappings USING btree (partner_name);


--
-- Name: idx_efactura_supplier_mappings_partner_name_unique; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE UNIQUE INDEX idx_efactura_supplier_mappings_partner_name_unique ON public.efactura_supplier_mappings USING btree (lower((partner_name)::text)) WHERE (is_active = true);


--
-- Name: idx_efactura_sync_runs_cif; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_efactura_sync_runs_cif ON public.efactura_sync_runs USING btree (company_cif);


--
-- Name: idx_entity_tags_entity; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_entity_tags_entity ON public.entity_tags USING btree (entity_type, entity_id);


--
-- Name: idx_entity_tags_tag; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_entity_tags_tag ON public.entity_tags USING btree (tag_id);


--
-- Name: idx_entity_tags_tagged_by; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_entity_tags_tagged_by ON public.entity_tags USING btree (tagged_by);


--
-- Name: idx_invoices_active_date; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_invoices_active_date ON public.invoices USING btree (invoice_date DESC) WHERE (deleted_at IS NULL);


--
-- Name: idx_invoices_created_at; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_invoices_created_at ON public.invoices USING btree (created_at DESC);


--
-- Name: idx_invoices_date; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_invoices_date ON public.invoices USING btree (invoice_date);


--
-- Name: idx_invoices_date_desc; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_invoices_date_desc ON public.invoices USING btree (invoice_date DESC);


--
-- Name: idx_invoices_deleted_at; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_invoices_deleted_at ON public.invoices USING btree (deleted_at);


--
-- Name: idx_invoices_deleted_date; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_invoices_deleted_date ON public.invoices USING btree (deleted_at, invoice_date DESC);


--
-- Name: idx_invoices_payment_status; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_invoices_payment_status ON public.invoices USING btree (payment_status);


--
-- Name: idx_invoices_status; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_invoices_status ON public.invoices USING btree (status);


--
-- Name: idx_invoices_supplier; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_invoices_supplier ON public.invoices USING btree (supplier);


--
-- Name: idx_notification_log_status; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_notification_log_status ON public.notification_log USING btree (status);


--
-- Name: idx_notifications_user_created; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_notifications_user_created ON public.notifications USING btree (user_id, created_at DESC);


--
-- Name: idx_notifications_user_unread; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_notifications_user_unread ON public.notifications USING btree (user_id, is_read) WHERE (is_read = false);


--
-- Name: idx_password_reset_tokens_token; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_password_reset_tokens_token ON public.password_reset_tokens USING btree (token);


--
-- Name: idx_performance_reports_created_at; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_performance_reports_created_at ON public.performance_reports USING btree (created_at DESC);


--
-- Name: idx_performance_reports_duration; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_performance_reports_duration ON public.performance_reports USING btree (duration_ms DESC);


--
-- Name: idx_performance_reports_endpoint; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_performance_reports_endpoint ON public.performance_reports USING btree (endpoint);


--
-- Name: idx_reinvoice_dest_allocation; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_reinvoice_dest_allocation ON public.reinvoice_destinations USING btree (allocation_id);


--
-- Name: idx_statements_hash; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_statements_hash ON public.bank_statements USING btree (file_hash);


--
-- Name: idx_tag_groups_name_unique; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE UNIQUE INDEX idx_tag_groups_name_unique ON public.tag_groups USING btree (lower((name)::text)) WHERE (is_active = true);


--
-- Name: idx_tags_global_name_unique; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE UNIQUE INDEX idx_tags_global_name_unique ON public.tags USING btree (lower((name)::text)) WHERE ((is_global = true) AND (is_active = true));


--
-- Name: idx_tags_user_name_unique; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE UNIQUE INDEX idx_tags_user_name_unique ON public.tags USING btree (created_by, lower((name)::text)) WHERE ((is_global = false) AND (is_active = true));


--
-- Name: idx_tags_visibility; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_tags_visibility ON public.tags USING btree (is_global, created_by) WHERE (is_active = true);


--
-- Name: idx_transactions_company; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_transactions_company ON public.bank_statement_transactions USING btree (company_cui);


--
-- Name: idx_transactions_date; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_transactions_date ON public.bank_statement_transactions USING btree (transaction_date);


--
-- Name: idx_transactions_status; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_transactions_status ON public.bank_statement_transactions USING btree (status);


--
-- Name: idx_transactions_supplier; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_transactions_supplier ON public.bank_statement_transactions USING btree (matched_supplier);


--
-- Name: idx_unique_transaction; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE UNIQUE INDEX idx_unique_transaction ON public.bank_statement_transactions USING btree (company_cui, transaction_date, amount, description) WHERE ((company_cui IS NOT NULL) AND (transaction_date IS NOT NULL) AND (amount IS NOT NULL) AND (description IS NOT NULL));


--
-- Name: idx_user_events_created_at; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_user_events_created_at ON public.user_events USING btree (created_at DESC);


--
-- Name: idx_user_events_event_type; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_user_events_event_type ON public.user_events USING btree (event_type);


--
-- Name: idx_user_events_user_id; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_user_events_user_id ON public.user_events USING btree (user_id);


--
-- Name: idx_user_filter_presets_unique_name; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE UNIQUE INDEX idx_user_filter_presets_unique_name ON public.user_filter_presets USING btree (user_id, page_key, lower((name)::text));


--
-- Name: idx_user_filter_presets_user_page; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_user_filter_presets_user_page ON public.user_filter_presets USING btree (user_id, page_key);


--
-- Name: idx_users_role_id; Type: INDEX; Schema: public; Owner: doadmin
--

CREATE INDEX idx_users_role_id ON public.users USING btree (role_id);


--
-- Name: conversation_contexts conversation_contexts_message_id_fkey; Type: FK CONSTRAINT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.conversation_contexts
    ADD CONSTRAINT conversation_contexts_message_id_fkey FOREIGN KEY (message_id) REFERENCES ai_agent.messages(id) ON DELETE CASCADE;


--
-- Name: conversation_logs conversation_logs_conversation_id_fkey; Type: FK CONSTRAINT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.conversation_logs
    ADD CONSTRAINT conversation_logs_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES ai_agent.conversations(id) ON DELETE SET NULL;


--
-- Name: conversation_logs conversation_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.conversation_logs
    ADD CONSTRAINT conversation_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: conversations conversations_model_config_id_fkey; Type: FK CONSTRAINT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.conversations
    ADD CONSTRAINT conversations_model_config_id_fkey FOREIGN KEY (model_config_id) REFERENCES ai_agent.model_configs(id);


--
-- Name: conversations conversations_user_id_fkey; Type: FK CONSTRAINT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.conversations
    ADD CONSTRAINT conversations_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: messages messages_conversation_id_fkey; Type: FK CONSTRAINT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.messages
    ADD CONSTRAINT messages_conversation_id_fkey FOREIGN KEY (conversation_id) REFERENCES ai_agent.conversations(id) ON DELETE CASCADE;


--
-- Name: messages messages_model_config_id_fkey; Type: FK CONSTRAINT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.messages
    ADD CONSTRAINT messages_model_config_id_fkey FOREIGN KEY (model_config_id) REFERENCES ai_agent.model_configs(id);


--
-- Name: rag_documents rag_documents_company_id_fkey; Type: FK CONSTRAINT; Schema: ai_agent; Owner: doadmin
--

ALTER TABLE ONLY ai_agent.rag_documents
    ADD CONSTRAINT rag_documents_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id);


--
-- Name: event_bonuses event_bonuses_created_by_fkey; Type: FK CONSTRAINT; Schema: hr; Owner: doadmin
--

ALTER TABLE ONLY hr.event_bonuses
    ADD CONSTRAINT event_bonuses_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: event_bonuses event_bonuses_event_id_fkey; Type: FK CONSTRAINT; Schema: hr; Owner: doadmin
--

ALTER TABLE ONLY hr.event_bonuses
    ADD CONSTRAINT event_bonuses_event_id_fkey FOREIGN KEY (event_id) REFERENCES hr.events(id) ON DELETE CASCADE;


--
-- Name: event_bonuses event_bonuses_user_id_fkey; Type: FK CONSTRAINT; Schema: hr; Owner: doadmin
--

ALTER TABLE ONLY hr.event_bonuses
    ADD CONSTRAINT event_bonuses_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: events events_created_by_fkey; Type: FK CONSTRAINT; Schema: hr; Owner: doadmin
--

ALTER TABLE ONLY hr.events
    ADD CONSTRAINT events_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: allocations allocations_invoice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.allocations
    ADD CONSTRAINT allocations_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.invoices(id) ON DELETE CASCADE;


--
-- Name: allocations allocations_responsible_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.allocations
    ADD CONSTRAINT allocations_responsible_user_id_fkey FOREIGN KEY (responsible_user_id) REFERENCES public.users(id);


--
-- Name: approval_audit_log approval_audit_log_actor_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_audit_log
    ADD CONSTRAINT approval_audit_log_actor_id_fkey FOREIGN KEY (actor_id) REFERENCES public.users(id);


--
-- Name: approval_audit_log approval_audit_log_request_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_audit_log
    ADD CONSTRAINT approval_audit_log_request_id_fkey FOREIGN KEY (request_id) REFERENCES public.approval_requests(id);


--
-- Name: approval_decisions approval_decisions_decided_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_decisions
    ADD CONSTRAINT approval_decisions_decided_by_fkey FOREIGN KEY (decided_by) REFERENCES public.users(id);


--
-- Name: approval_decisions approval_decisions_delegated_to_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_decisions
    ADD CONSTRAINT approval_decisions_delegated_to_fkey FOREIGN KEY (delegated_to) REFERENCES public.users(id);


--
-- Name: approval_decisions approval_decisions_request_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_decisions
    ADD CONSTRAINT approval_decisions_request_id_fkey FOREIGN KEY (request_id) REFERENCES public.approval_requests(id) ON DELETE CASCADE;


--
-- Name: approval_decisions approval_decisions_step_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_decisions
    ADD CONSTRAINT approval_decisions_step_id_fkey FOREIGN KEY (step_id) REFERENCES public.approval_steps(id);


--
-- Name: approval_delegations approval_delegations_delegate_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_delegations
    ADD CONSTRAINT approval_delegations_delegate_id_fkey FOREIGN KEY (delegate_id) REFERENCES public.users(id);


--
-- Name: approval_delegations approval_delegations_delegator_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_delegations
    ADD CONSTRAINT approval_delegations_delegator_id_fkey FOREIGN KEY (delegator_id) REFERENCES public.users(id);


--
-- Name: approval_delegations approval_delegations_flow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_delegations
    ADD CONSTRAINT approval_delegations_flow_id_fkey FOREIGN KEY (flow_id) REFERENCES public.approval_flows(id);


--
-- Name: approval_flows approval_flows_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_flows
    ADD CONSTRAINT approval_flows_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: approval_requests approval_requests_current_step_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT approval_requests_current_step_id_fkey FOREIGN KEY (current_step_id) REFERENCES public.approval_steps(id);


--
-- Name: approval_requests approval_requests_flow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT approval_requests_flow_id_fkey FOREIGN KEY (flow_id) REFERENCES public.approval_flows(id);


--
-- Name: approval_requests approval_requests_requested_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_requests
    ADD CONSTRAINT approval_requests_requested_by_fkey FOREIGN KEY (requested_by) REFERENCES public.users(id);


--
-- Name: approval_steps approval_steps_approver_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_steps
    ADD CONSTRAINT approval_steps_approver_user_id_fkey FOREIGN KEY (approver_user_id) REFERENCES public.users(id);


--
-- Name: approval_steps approval_steps_escalation_step_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_steps
    ADD CONSTRAINT approval_steps_escalation_step_id_fkey FOREIGN KEY (escalation_step_id) REFERENCES public.approval_steps(id);


--
-- Name: approval_steps approval_steps_escalation_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_steps
    ADD CONSTRAINT approval_steps_escalation_user_id_fkey FOREIGN KEY (escalation_user_id) REFERENCES public.users(id);


--
-- Name: approval_steps approval_steps_flow_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.approval_steps
    ADD CONSTRAINT approval_steps_flow_id_fkey FOREIGN KEY (flow_id) REFERENCES public.approval_flows(id) ON DELETE CASCADE;


--
-- Name: auto_tag_rules auto_tag_rules_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.auto_tag_rules
    ADD CONSTRAINT auto_tag_rules_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: auto_tag_rules auto_tag_rules_tag_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.auto_tag_rules
    ADD CONSTRAINT auto_tag_rules_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES public.tags(id) ON DELETE CASCADE;


--
-- Name: bank_statement_transactions bank_statement_transactions_invoice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.bank_statement_transactions
    ADD CONSTRAINT bank_statement_transactions_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.invoices(id) ON DELETE SET NULL;


--
-- Name: bank_statement_transactions bank_statement_transactions_merged_into_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.bank_statement_transactions
    ADD CONSTRAINT bank_statement_transactions_merged_into_id_fkey FOREIGN KEY (merged_into_id) REFERENCES public.bank_statement_transactions(id) ON DELETE SET NULL;


--
-- Name: bank_statement_transactions bank_statement_transactions_statement_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.bank_statement_transactions
    ADD CONSTRAINT bank_statement_transactions_statement_id_fkey FOREIGN KEY (statement_id) REFERENCES public.bank_statements(id) ON DELETE SET NULL;


--
-- Name: bank_statement_transactions bank_statement_transactions_suggested_invoice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.bank_statement_transactions
    ADD CONSTRAINT bank_statement_transactions_suggested_invoice_id_fkey FOREIGN KEY (suggested_invoice_id) REFERENCES public.invoices(id) ON DELETE SET NULL;


--
-- Name: bank_statements bank_statements_uploaded_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.bank_statements
    ADD CONSTRAINT bank_statements_uploaded_by_fkey FOREIGN KEY (uploaded_by) REFERENCES public.users(id);


--
-- Name: company_brands company_brands_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.company_brands
    ADD CONSTRAINT company_brands_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id) ON DELETE CASCADE;


--
-- Name: connector_sync_log connector_sync_log_connector_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.connector_sync_log
    ADD CONSTRAINT connector_sync_log_connector_id_fkey FOREIGN KEY (connector_id) REFERENCES public.connectors(id) ON DELETE CASCADE;


--
-- Name: department_structure department_structure_manager_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.department_structure
    ADD CONSTRAINT department_structure_manager_user_id_fkey FOREIGN KEY (manager_user_id) REFERENCES public.users(id);


--
-- Name: department_structure department_structure_responsable_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.department_structure
    ADD CONSTRAINT department_structure_responsable_id_fkey FOREIGN KEY (responsable_id) REFERENCES public.users(id);


--
-- Name: efactura_invoice_artifacts efactura_invoice_artifacts_invoice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_invoice_artifacts
    ADD CONSTRAINT efactura_invoice_artifacts_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.efactura_invoices(id) ON DELETE CASCADE;


--
-- Name: efactura_invoice_refs efactura_invoice_refs_invoice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_invoice_refs
    ADD CONSTRAINT efactura_invoice_refs_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.efactura_invoices(id) ON DELETE CASCADE;


--
-- Name: efactura_invoices efactura_invoices_company_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_invoices
    ADD CONSTRAINT efactura_invoices_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id);


--
-- Name: efactura_invoices efactura_invoices_jarvis_invoice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_invoices
    ADD CONSTRAINT efactura_invoices_jarvis_invoice_id_fkey FOREIGN KEY (jarvis_invoice_id) REFERENCES public.invoices(id) ON DELETE SET NULL;


--
-- Name: efactura_supplier_mapping_types efactura_supplier_mapping_types_mapping_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_supplier_mapping_types
    ADD CONSTRAINT efactura_supplier_mapping_types_mapping_id_fkey FOREIGN KEY (mapping_id) REFERENCES public.efactura_supplier_mappings(id) ON DELETE CASCADE;


--
-- Name: efactura_supplier_mapping_types efactura_supplier_mapping_types_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_supplier_mapping_types
    ADD CONSTRAINT efactura_supplier_mapping_types_type_id_fkey FOREIGN KEY (type_id) REFERENCES public.efactura_supplier_types(id) ON DELETE CASCADE;


--
-- Name: efactura_supplier_mappings efactura_supplier_mappings_type_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_supplier_mappings
    ADD CONSTRAINT efactura_supplier_mappings_type_id_fkey FOREIGN KEY (type_id) REFERENCES public.efactura_supplier_types(id);


--
-- Name: entity_tags entity_tags_tag_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.entity_tags
    ADD CONSTRAINT entity_tags_tag_id_fkey FOREIGN KEY (tag_id) REFERENCES public.tags(id) ON DELETE CASCADE;


--
-- Name: entity_tags entity_tags_tagged_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.entity_tags
    ADD CONSTRAINT entity_tags_tagged_by_fkey FOREIGN KEY (tagged_by) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: company_brands fk_company_brands_brand; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.company_brands
    ADD CONSTRAINT fk_company_brands_brand FOREIGN KEY (brand_id) REFERENCES public.brands(id);


--
-- Name: efactura_sync_errors fk_sync_errors_run_id; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.efactura_sync_errors
    ADD CONSTRAINT fk_sync_errors_run_id FOREIGN KEY (run_id) REFERENCES public.efactura_sync_runs(run_id);


--
-- Name: module_menu_items module_menu_items_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.module_menu_items
    ADD CONSTRAINT module_menu_items_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.module_menu_items(id) ON DELETE CASCADE;


--
-- Name: notification_log notification_log_invoice_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.notification_log
    ADD CONSTRAINT notification_log_invoice_id_fkey FOREIGN KEY (invoice_id) REFERENCES public.invoices(id) ON DELETE CASCADE;


--
-- Name: notification_log notification_log_responsable_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.notification_log
    ADD CONSTRAINT notification_log_responsable_id_fkey FOREIGN KEY (responsable_id) REFERENCES public.users(id);


--
-- Name: notifications notifications_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.notifications
    ADD CONSTRAINT notifications_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: password_reset_tokens password_reset_tokens_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.password_reset_tokens
    ADD CONSTRAINT password_reset_tokens_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: performance_reports performance_reports_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.performance_reports
    ADD CONSTRAINT performance_reports_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: permissions permissions_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.permissions
    ADD CONSTRAINT permissions_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.permissions(id) ON DELETE SET NULL;


--
-- Name: reinvoice_destinations reinvoice_destinations_allocation_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.reinvoice_destinations
    ADD CONSTRAINT reinvoice_destinations_allocation_id_fkey FOREIGN KEY (allocation_id) REFERENCES public.allocations(id) ON DELETE CASCADE;


--
-- Name: role_permissions role_permissions_permission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_permission_id_fkey FOREIGN KEY (permission_id) REFERENCES public.permissions(id) ON DELETE CASCADE;


--
-- Name: role_permissions role_permissions_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.role_permissions
    ADD CONSTRAINT role_permissions_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE CASCADE;


--
-- Name: role_permissions_v2 role_permissions_v2_permission_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.role_permissions_v2
    ADD CONSTRAINT role_permissions_v2_permission_id_fkey FOREIGN KEY (permission_id) REFERENCES public.permissions_v2(id) ON DELETE CASCADE;


--
-- Name: role_permissions_v2 role_permissions_v2_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.role_permissions_v2
    ADD CONSTRAINT role_permissions_v2_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id) ON DELETE CASCADE;


--
-- Name: tags tags_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: tags tags_group_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.tags
    ADD CONSTRAINT tags_group_id_fkey FOREIGN KEY (group_id) REFERENCES public.tag_groups(id) ON DELETE SET NULL;


--
-- Name: user_events user_events_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.user_events
    ADD CONSTRAINT user_events_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE SET NULL;


--
-- Name: user_filter_presets user_filter_presets_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.user_filter_presets
    ADD CONSTRAINT user_filter_presets_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id) ON DELETE CASCADE;


--
-- Name: users users_org_unit_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_org_unit_id_fkey FOREIGN KEY (org_unit_id) REFERENCES public.department_structure(id);


--
-- Name: users users_role_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_role_id_fkey FOREIGN KEY (role_id) REFERENCES public.roles(id);


--
-- Name: vendor_mappings vendor_mappings_template_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: doadmin
--

ALTER TABLE ONLY public.vendor_mappings
    ADD CONSTRAINT vendor_mappings_template_id_fkey FOREIGN KEY (template_id) REFERENCES public.invoice_templates(id) ON DELETE SET NULL;


--
-- Name: SCHEMA public; Type: ACL; Schema: -; Owner: doadmin
--

REVOKE USAGE ON SCHEMA public FROM PUBLIC;
GRANT ALL ON SCHEMA public TO PUBLIC;


--
-- PostgreSQL database dump complete
--

\unrestrict rQ5wibgOns0oFgQ80cIMJS7B6qWQCd7L8BUV5Mrg1riCZnlfeudMLU6k13OOxcp

