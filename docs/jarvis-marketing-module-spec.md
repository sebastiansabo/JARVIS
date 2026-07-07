# JARVIS Marketing Projects Module — Implementation Prompt

## Context

You are building the **Marketing Projects Module** for JARVIS. This is the first business module that consumes both the **Approval Engine** and the **Notification Engine** already deployed in the database.

**Tech Stack:** Flask (sync), raw SQL + psycopg2, Vite + React 19, session auth + permissions_v2, SERIAL integer PKs.

**Critical constraint:** Do NOT alter any existing tables. All new tables go in the `public` schema following existing conventions exactly.

---

## Existing Tables This Module Reuses (DO NOT MODIFY)

```
brands              (id, name, is_active)
companies           (id, company, vat)
company_brands      (id, company_id, brand_id, is_active)
department_structure (id, company, brand, department, subdepartment, manager, 
                      responsable_id, manager_ids[], marketing_ids[], company_id, manager_user_id)
departments         (id, name, is_active)
subdepartments      (id, name, is_active)
users               (id, name, email, role_id, company, brand, department, subdepartment, org_unit_id, is_active)
roles               (id, name, description, ...)
permissions_v2      (id, module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, is_scope_based)
role_permissions_v2 (id, role_id, permission_id, scope [deny/own/department/all], granted)
notifications       (id, user_id, type, title, message, link, entity_type, entity_id, is_read)
entity_tags         (id, tag_id, entity_type, entity_id, tagged_by)
tags                (id, name, group_id, color, icon, is_global, created_by)
tag_groups          (id, name, color)
dropdown_options    (id, dropdown_type, value, label, color, sort_order, is_active)
approval_flows      (id, name, slug, entity_type, trigger_conditions, ...)
approval_requests   (id, entity_type, entity_id, flow_id, current_step_id, status, context_snapshot, ...)
approval_decisions  (id, request_id, step_id, decided_by, decision, comment, conditions, ...)
approval_audit_log  (id, request_id, action, actor_id, details, ...)
```

---

## New Tables

### mkt_projects (Core entity)

```sql
CREATE TABLE public.mkt_projects (
    id integer NOT NULL,
    name text NOT NULL,
    slug text NOT NULL,
    description text,
    
    -- Organizational anchoring (references existing structure)
    company_id integer NOT NULL,                -- FK companies(id)
    brand_id integer,                           -- FK brands(id), NULL = corporate/multi-brand
    department_structure_id integer,             -- FK department_structure(id), ties to org chart
    
    -- Classification
    project_type text NOT NULL DEFAULT 'campaign',  -- campaign, always_on, event, launch, branding, research
    channel_mix text[] DEFAULT '{}',            -- {'meta_ads','google_ads','radio','print','ooh','influencer','email','sms','events'}
    
    -- Lifecycle
    status text NOT NULL DEFAULT 'draft',       -- draft, pending_approval, approved, active, paused, completed, archived, cancelled
    start_date date,
    end_date date,
    
    -- Budget
    total_budget numeric(15,2) NOT NULL DEFAULT 0,
    currency text NOT NULL DEFAULT 'RON',
    
    -- Ownership
    owner_id integer NOT NULL,                  -- FK users(id), project manager
    created_by integer NOT NULL,                -- FK users(id)
    
    -- Objective & brief
    objective text,                             -- What success looks like
    target_audience text,                       -- Who we're targeting
    brief jsonb DEFAULT '{}'::jsonb,            -- Flexible brief data: key messages, assets, references
    
    -- Metadata
    external_ref text,                          -- Client PO number, agency reference, etc.
    metadata jsonb DEFAULT '{}'::jsonb,
    
    -- Timestamps
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    deleted_at timestamp without time zone,     -- Soft delete (matches invoices pattern)
    
    CONSTRAINT mkt_projects_status_check CHECK (status = ANY (ARRAY[
        'draft'::text, 'pending_approval'::text, 'approved'::text, 'active'::text,
        'paused'::text, 'completed'::text, 'archived'::text, 'cancelled'::text
    ])),
    CONSTRAINT mkt_projects_type_check CHECK (project_type = ANY (ARRAY[
        'campaign'::text, 'always_on'::text, 'event'::text, 'launch'::text,
        'branding'::text, 'research'::text
    ]))
);

CREATE SEQUENCE public.mkt_projects_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.mkt_projects_id_seq OWNED BY public.mkt_projects.id;
ALTER TABLE ONLY public.mkt_projects ALTER COLUMN id SET DEFAULT nextval('public.mkt_projects_id_seq'::regclass);
ALTER TABLE ONLY public.mkt_projects ADD CONSTRAINT mkt_projects_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.mkt_projects ADD CONSTRAINT mkt_projects_slug_key UNIQUE (slug);

ALTER TABLE ONLY public.mkt_projects ADD CONSTRAINT mkt_projects_company_id_fkey FOREIGN KEY (company_id) REFERENCES public.companies(id);
ALTER TABLE ONLY public.mkt_projects ADD CONSTRAINT mkt_projects_brand_id_fkey FOREIGN KEY (brand_id) REFERENCES public.brands(id);
ALTER TABLE ONLY public.mkt_projects ADD CONSTRAINT mkt_projects_dept_struct_id_fkey FOREIGN KEY (department_structure_id) REFERENCES public.department_structure(id);
ALTER TABLE ONLY public.mkt_projects ADD CONSTRAINT mkt_projects_owner_id_fkey FOREIGN KEY (owner_id) REFERENCES public.users(id);
ALTER TABLE ONLY public.mkt_projects ADD CONSTRAINT mkt_projects_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);

CREATE INDEX ix_mkt_projects_company ON public.mkt_projects(company_id);
CREATE INDEX ix_mkt_projects_brand ON public.mkt_projects(brand_id);
CREATE INDEX ix_mkt_projects_status ON public.mkt_projects(status) WHERE deleted_at IS NULL;
CREATE INDEX ix_mkt_projects_owner ON public.mkt_projects(owner_id);
CREATE INDEX ix_mkt_projects_dates ON public.mkt_projects(start_date, end_date) WHERE deleted_at IS NULL;
```

### mkt_project_members (Team assignments)

```sql
CREATE TABLE public.mkt_project_members (
    id integer NOT NULL,
    project_id integer NOT NULL,
    user_id integer NOT NULL,
    role text NOT NULL DEFAULT 'member',        -- owner, manager, specialist, viewer, agency
    department_structure_id integer,             -- Which org unit this person represents
    added_by integer NOT NULL,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT mkt_project_members_role_check CHECK (role = ANY (ARRAY[
        'owner'::text, 'manager'::text, 'specialist'::text, 'viewer'::text, 'agency'::text
    ]))
);

CREATE SEQUENCE public.mkt_project_members_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.mkt_project_members_id_seq OWNED BY public.mkt_project_members.id;
ALTER TABLE ONLY public.mkt_project_members ALTER COLUMN id SET DEFAULT nextval('public.mkt_project_members_id_seq'::regclass);
ALTER TABLE ONLY public.mkt_project_members ADD CONSTRAINT mkt_project_members_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.mkt_project_members ADD CONSTRAINT mkt_project_members_unique UNIQUE (project_id, user_id);

ALTER TABLE ONLY public.mkt_project_members ADD CONSTRAINT mkt_project_members_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.mkt_projects(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.mkt_project_members ADD CONSTRAINT mkt_project_members_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);
ALTER TABLE ONLY public.mkt_project_members ADD CONSTRAINT mkt_project_members_added_by_fkey FOREIGN KEY (added_by) REFERENCES public.users(id);

CREATE INDEX ix_mkt_project_members_user ON public.mkt_project_members(user_id);
```

### mkt_budget_lines (Per-channel budget allocation)

```sql
CREATE TABLE public.mkt_budget_lines (
    id integer NOT NULL,
    project_id integer NOT NULL,
    
    -- What
    channel text NOT NULL,                      -- meta_ads, google_ads, radio, print, ooh, influencer, email, events, other
    description text,                           -- "Google Search - Brand Terms", "Radio Cluj - Morning Slot"
    
    -- Who executes
    department_structure_id integer,             -- Which dept is responsible for execution
    agency_name text,                           -- External agency if applicable
    
    -- Budget
    planned_amount numeric(15,2) NOT NULL DEFAULT 0,
    approved_amount numeric(15,2) DEFAULT 0,    -- Set after approval
    spent_amount numeric(15,2) DEFAULT 0,       -- Actual spend (manual or synced)
    currency text NOT NULL DEFAULT 'RON',
    
    -- Period
    period_type text DEFAULT 'campaign',        -- campaign (lifetime), monthly, quarterly
    period_start date,
    period_end date,
    
    -- Status
    status text NOT NULL DEFAULT 'draft',       -- draft, pending_approval, approved, active, exhausted, cancelled
    
    notes text,
    metadata jsonb DEFAULT '{}'::jsonb,
    
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT mkt_budget_lines_status_check CHECK (status = ANY (ARRAY[
        'draft'::text, 'pending_approval'::text, 'approved'::text, 
        'active'::text, 'exhausted'::text, 'cancelled'::text
    ]))
);

CREATE SEQUENCE public.mkt_budget_lines_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.mkt_budget_lines_id_seq OWNED BY public.mkt_budget_lines.id;
ALTER TABLE ONLY public.mkt_budget_lines ALTER COLUMN id SET DEFAULT nextval('public.mkt_budget_lines_id_seq'::regclass);
ALTER TABLE ONLY public.mkt_budget_lines ADD CONSTRAINT mkt_budget_lines_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.mkt_budget_lines ADD CONSTRAINT mkt_budget_lines_project_id_fkey FOREIGN KEY (project_id) REFERENCES public.mkt_projects(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.mkt_budget_lines ADD CONSTRAINT mkt_budget_lines_dept_struct_fkey FOREIGN KEY (department_structure_id) REFERENCES public.department_structure(id);

CREATE INDEX ix_mkt_budget_lines_project ON public.mkt_budget_lines(project_id);
CREATE INDEX ix_mkt_budget_lines_channel ON public.mkt_budget_lines(channel);
```

### mkt_budget_transactions (Spend tracking / actuals)

```sql
CREATE TABLE public.mkt_budget_transactions (
    id integer NOT NULL,
    budget_line_id integer NOT NULL,
    
    amount numeric(15,2) NOT NULL,
    direction text NOT NULL DEFAULT 'debit',    -- debit (spend) or credit (refund/adjustment)
    
    -- Source tracking
    source text NOT NULL DEFAULT 'manual',      -- manual, meta_api, google_api, invoice_link
    reference_id text,                          -- Invoice number, ad account ID, campaign ID
    invoice_id integer,                         -- FK invoices(id) if linked to JARVIS invoice
    
    transaction_date date NOT NULL,
    description text,
    
    recorded_by integer NOT NULL,               -- FK users(id)
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT mkt_budget_tx_direction_check CHECK (direction = ANY (ARRAY['debit'::text, 'credit'::text]))
);

CREATE SEQUENCE public.mkt_budget_transactions_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.mkt_budget_transactions_id_seq OWNED BY public.mkt_budget_transactions.id;
ALTER TABLE ONLY public.mkt_budget_transactions ALTER COLUMN id SET DEFAULT nextval('public.mkt_budget_transactions_id_seq'::regclass);
ALTER TABLE ONLY public.mkt_budget_transactions ADD CONSTRAINT mkt_budget_transactions_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.mkt_budget_transactions ADD CONSTRAINT mkt_budget_tx_budget_line_fkey FOREIGN KEY (budget_line_id) REFERENCES public.mkt_budget_lines(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.mkt_budget_transactions ADD CONSTRAINT mkt_budget_tx_invoice_fkey FOREIGN KEY (invoice_id) REFERENCES public.invoices(id) ON DELETE SET NULL;
ALTER TABLE ONLY public.mkt_budget_transactions ADD CONSTRAINT mkt_budget_tx_recorded_by_fkey FOREIGN KEY (recorded_by) REFERENCES public.users(id);

CREATE INDEX ix_mkt_budget_tx_line ON public.mkt_budget_transactions(budget_line_id);
CREATE INDEX ix_mkt_budget_tx_date ON public.mkt_budget_transactions(transaction_date);
```

### mkt_kpi_definitions (Master KPI catalog)

```sql
CREATE TABLE public.mkt_kpi_definitions (
    id integer NOT NULL,
    name text NOT NULL,                         -- CPA, ROAS, CPL, CTR, Leads, Sales, Impressions, Reach
    slug text NOT NULL,
    unit text NOT NULL DEFAULT 'number',        -- number, currency, percentage, ratio
    direction text NOT NULL DEFAULT 'higher',   -- higher (higher_is_better), lower (lower_is_better)
    category text NOT NULL DEFAULT 'performance', -- performance, brand, engagement, financial, conversion
    formula text,                               -- Optional: "spent / conversions", "revenue / spent"
    description text,
    is_active boolean DEFAULT true,
    sort_order integer DEFAULT 0,
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);

CREATE SEQUENCE public.mkt_kpi_definitions_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.mkt_kpi_definitions_id_seq OWNED BY public.mkt_kpi_definitions.id;
ALTER TABLE ONLY public.mkt_kpi_definitions ALTER COLUMN id SET DEFAULT nextval('public.mkt_kpi_definitions_id_seq'::regclass);
ALTER TABLE ONLY public.mkt_kpi_definitions ADD CONSTRAINT mkt_kpi_definitions_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.mkt_kpi_definitions ADD CONSTRAINT mkt_kpi_definitions_slug_key UNIQUE (slug);
```

### mkt_project_kpis (KPI targets and actuals per project)

```sql
CREATE TABLE public.mkt_project_kpis (
    id integer NOT NULL,
    project_id integer NOT NULL,
    kpi_definition_id integer NOT NULL,
    
    channel text,                               -- NULL = project-wide, or specific channel
    
    target_value numeric(15,4),
    current_value numeric(15,4) DEFAULT 0,
    
    weight integer DEFAULT 50,                  -- 0-100, importance within project
    
    -- Alert thresholds
    threshold_warning numeric(15,4),            -- Yellow alert
    threshold_critical numeric(15,4),           -- Red alert
    
    -- Auto-computed status
    status text DEFAULT 'no_data',              -- no_data, on_track, at_risk, behind, exceeded
    
    last_synced_at timestamp without time zone,
    notes text,
    
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT mkt_project_kpis_status_check CHECK (status = ANY (ARRAY[
        'no_data'::text, 'on_track'::text, 'at_risk'::text, 'behind'::text, 'exceeded'::text
    ]))
);

CREATE SEQUENCE public.mkt_project_kpis_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.mkt_project_kpis_id_seq OWNED BY public.mkt_project_kpis.id;
ALTER TABLE ONLY public.mkt_project_kpis ALTER COLUMN id SET DEFAULT nextval('public.mkt_project_kpis_id_seq'::regclass);
ALTER TABLE ONLY public.mkt_project_kpis ADD CONSTRAINT mkt_project_kpis_pkey PRIMARY KEY (id);
ALTER TABLE ONLY public.mkt_project_kpis ADD CONSTRAINT mkt_project_kpis_unique UNIQUE (project_id, kpi_definition_id, channel);

ALTER TABLE ONLY public.mkt_project_kpis ADD CONSTRAINT mkt_project_kpis_project_fkey FOREIGN KEY (project_id) REFERENCES public.mkt_projects(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.mkt_project_kpis ADD CONSTRAINT mkt_project_kpis_def_fkey FOREIGN KEY (kpi_definition_id) REFERENCES public.mkt_kpi_definitions(id);

CREATE INDEX ix_mkt_project_kpis_project ON public.mkt_project_kpis(project_id);
```

### mkt_kpi_snapshots (Historical KPI values — time series)

```sql
CREATE TABLE public.mkt_kpi_snapshots (
    id integer NOT NULL,
    project_kpi_id integer NOT NULL,
    value numeric(15,4) NOT NULL,
    source text NOT NULL DEFAULT 'manual',      -- manual, api_sync, calculated
    recorded_at timestamp without time zone NOT NULL DEFAULT CURRENT_TIMESTAMP,
    recorded_by integer,                        -- NULL for system/api
    notes text
);

CREATE SEQUENCE public.mkt_kpi_snapshots_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.mkt_kpi_snapshots_id_seq OWNED BY public.mkt_kpi_snapshots.id;
ALTER TABLE ONLY public.mkt_kpi_snapshots ALTER COLUMN id SET DEFAULT nextval('public.mkt_kpi_snapshots_id_seq'::regclass);
ALTER TABLE ONLY public.mkt_kpi_snapshots ADD CONSTRAINT mkt_kpi_snapshots_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.mkt_kpi_snapshots ADD CONSTRAINT mkt_kpi_snapshots_kpi_fkey FOREIGN KEY (project_kpi_id) REFERENCES public.mkt_project_kpis(id) ON DELETE CASCADE;

CREATE INDEX ix_mkt_kpi_snapshots_kpi ON public.mkt_kpi_snapshots(project_kpi_id);
CREATE INDEX ix_mkt_kpi_snapshots_date ON public.mkt_kpi_snapshots(recorded_at);
```

### mkt_project_activity (Project-level audit trail)

```sql
CREATE TABLE public.mkt_project_activity (
    id integer NOT NULL,
    project_id integer NOT NULL,
    
    action text NOT NULL,
    -- 'created', 'updated', 'status_changed', 'budget_added', 'budget_modified',
    -- 'member_added', 'member_removed', 'kpi_updated', 'comment_added',
    -- 'approval_submitted', 'approval_decided', 'spend_recorded', 'file_attached'
    
    actor_id integer,                           -- FK users(id), NULL for system
    actor_type text DEFAULT 'user',             -- user, system, scheduler, api
    
    details jsonb DEFAULT '{}'::jsonb,
    -- {"field": "status", "from": "draft", "to": "active"}
    -- {"member_name": "Ion Popescu", "role": "specialist"}
    -- {"channel": "meta_ads", "amount": 5000}
    
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);

CREATE SEQUENCE public.mkt_project_activity_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.mkt_project_activity_id_seq OWNED BY public.mkt_project_activity.id;
ALTER TABLE ONLY public.mkt_project_activity ALTER COLUMN id SET DEFAULT nextval('public.mkt_project_activity_id_seq'::regclass);
ALTER TABLE ONLY public.mkt_project_activity ADD CONSTRAINT mkt_project_activity_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.mkt_project_activity ADD CONSTRAINT mkt_project_activity_project_fkey FOREIGN KEY (project_id) REFERENCES public.mkt_projects(id) ON DELETE CASCADE;

CREATE INDEX ix_mkt_project_activity_project ON public.mkt_project_activity(project_id);
CREATE INDEX ix_mkt_project_activity_date ON public.mkt_project_activity(created_at);
```

### mkt_project_comments (Discussion thread per project)

```sql
CREATE TABLE public.mkt_project_comments (
    id integer NOT NULL,
    project_id integer NOT NULL,
    parent_id integer,                          -- NULL = top-level, FK to self for replies
    user_id integer NOT NULL,
    content text NOT NULL,
    is_internal boolean DEFAULT false,          -- Internal note vs visible to all members
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    updated_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP,
    deleted_at timestamp without time zone       -- Soft delete
);

CREATE SEQUENCE public.mkt_project_comments_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.mkt_project_comments_id_seq OWNED BY public.mkt_project_comments.id;
ALTER TABLE ONLY public.mkt_project_comments ALTER COLUMN id SET DEFAULT nextval('public.mkt_project_comments_id_seq'::regclass);
ALTER TABLE ONLY public.mkt_project_comments ADD CONSTRAINT mkt_project_comments_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.mkt_project_comments ADD CONSTRAINT mkt_project_comments_project_fkey FOREIGN KEY (project_id) REFERENCES public.mkt_projects(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.mkt_project_comments ADD CONSTRAINT mkt_project_comments_parent_fkey FOREIGN KEY (parent_id) REFERENCES public.mkt_project_comments(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.mkt_project_comments ADD CONSTRAINT mkt_project_comments_user_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);

CREATE INDEX ix_mkt_project_comments_project ON public.mkt_project_comments(project_id);
```

### mkt_project_files (Attachments / deliverables)

```sql
CREATE TABLE public.mkt_project_files (
    id integer NOT NULL,
    project_id integer NOT NULL,
    
    file_name text NOT NULL,
    file_type text,                             -- brief, creative, report, media_plan, invoice, other
    mime_type text,
    file_size integer,
    storage_uri text NOT NULL,                  -- Google Drive link, S3 path, local path
    
    uploaded_by integer NOT NULL,
    description text,
    
    created_at timestamp without time zone DEFAULT CURRENT_TIMESTAMP
);

CREATE SEQUENCE public.mkt_project_files_id_seq AS integer START WITH 1 INCREMENT BY 1 NO MINVALUE NO MAXVALUE CACHE 1;
ALTER SEQUENCE public.mkt_project_files_id_seq OWNED BY public.mkt_project_files.id;
ALTER TABLE ONLY public.mkt_project_files ALTER COLUMN id SET DEFAULT nextval('public.mkt_project_files_id_seq'::regclass);
ALTER TABLE ONLY public.mkt_project_files ADD CONSTRAINT mkt_project_files_pkey PRIMARY KEY (id);

ALTER TABLE ONLY public.mkt_project_files ADD CONSTRAINT mkt_project_files_project_fkey FOREIGN KEY (project_id) REFERENCES public.mkt_projects(id) ON DELETE CASCADE;
ALTER TABLE ONLY public.mkt_project_files ADD CONSTRAINT mkt_project_files_user_fkey FOREIGN KEY (uploaded_by) REFERENCES public.users(id);

CREATE INDEX ix_mkt_project_files_project ON public.mkt_project_files(project_id);
```

---

## Integration Points

### 1. Approval Engine Integration

The marketing module submits projects for approval via `entity_type = 'mkt_project'`. Context snapshot includes what approvers need to decide:

```python
# When user clicks "Submit for Approval"
context = {
    "title": project['name'],
    "amount": project['total_budget'],
    "currency": project['currency'],
    "project_type": project['project_type'],
    "company": company_name,
    "brand": brand_name,
    "owner": owner_name,
    "channels": project['channel_mix'],
    "start_date": str(project['start_date']),
    "end_date": str(project['end_date']),
    "objective": project['objective'],
    "budget_breakdown": [
        {"channel": line['channel'], "amount": float(line['planned_amount'])}
        for line in budget_lines
    ]
}

approval_engine.submit(
    entity_type='mkt_project',
    entity_id=project['id'],
    context=context,
    requested_by=current_user_id,
    priority='normal'
)

# Also update project status
UPDATE mkt_projects SET status = 'pending_approval', updated_at = NOW() WHERE id = %s
```

**Approval event handlers for marketing module:**

```python
@on('approval.approved')
def handle_mkt_project_approved(payload):
    if payload['entity_type'] != 'mkt_project':
        return
    project_id = payload['entity_id']
    
    # Activate project
    execute_query(
        "UPDATE mkt_projects SET status = 'approved', updated_at = NOW() WHERE id = %s",
        (project_id,)
    )
    # Set approved_amount on all budget lines
    execute_query(
        """UPDATE mkt_budget_lines 
           SET approved_amount = planned_amount, status = 'approved', updated_at = NOW() 
           WHERE project_id = %s AND status = 'draft'""",
        (project_id,)
    )
    # Log activity
    execute_query(
        """INSERT INTO mkt_project_activity (project_id, action, actor_type, details)
           VALUES (%s, 'approval_decided', 'system', %s)""",
        (project_id, json.dumps({"decision": "approved"}))
    )

@on('approval.rejected')
def handle_mkt_project_rejected(payload):
    if payload['entity_type'] != 'mkt_project':
        return
    execute_query(
        "UPDATE mkt_projects SET status = 'draft', updated_at = NOW() WHERE id = %s",
        (payload['entity_id'],)
    )
```

**Seed approval flows for marketing:**

```sql
-- Marketing project approval flow
INSERT INTO approval_flows (name, slug, entity_type, trigger_conditions, priority, created_by)
VALUES ('Marketing Project Approval', 'mkt-project-approval', 'mkt_project', '{}', 0, 1);

-- Steps: Marketing Director → Finance (if >5k) → CEO (if >20k)
INSERT INTO approval_steps (flow_id, name, step_order, approver_type, approver_role_name, timeout_hours)
VALUES 
    ((SELECT id FROM approval_flows WHERE slug = 'mkt-project-approval'), 'Marketing Director', 1, 'role', 'marketing_director', 48);

INSERT INTO approval_steps (flow_id, name, step_order, approver_type, approver_role_name, timeout_hours, skip_conditions)
VALUES 
    ((SELECT id FROM approval_flows WHERE slug = 'mkt-project-approval'), 'Finance Review', 2, 'role', 'finance_manager', 72, '{"amount_lt": 5000}');

INSERT INTO approval_steps (flow_id, name, step_order, approver_type, approver_role_name, skip_conditions)
VALUES 
    ((SELECT id FROM approval_flows WHERE slug = 'mkt-project-approval'), 'CEO Approval', 3, 'role', 'ceo', '{"amount_lt": 20000}');
```

### 2. Notification Integration

Uses existing `notifications` table directly:

```python
# Notify team members when project is approved
def notify_project_team(project_id, title, message, link):
    members = execute_query(
        "SELECT user_id FROM mkt_project_members WHERE project_id = %s",
        (project_id,), fetch_all=True
    )
    for member in (members or []):
        execute_query(
            """INSERT INTO notifications (user_id, type, title, message, link, entity_type, entity_id)
               VALUES (%s, 'success', %s, %s, %s, 'mkt_project', %s)""",
            (member['user_id'], title, message, link, project_id)
        )
```

### 3. Tagging Integration

Uses existing `entity_tags` system. Entity type = `'mkt_project'`:

```python
# Tag a project
INSERT INTO entity_tags (tag_id, entity_type, entity_id, tagged_by) VALUES (%s, 'mkt_project', %s, %s)

# Get tags for a project
SELECT t.id, t.name, t.color, tg.name as group_name
FROM entity_tags et
JOIN tags t ON et.tag_id = t.id
LEFT JOIN tag_groups tg ON t.group_id = tg.id
WHERE et.entity_type = 'mkt_project' AND et.entity_id = %s
```

### 4. Dropdown Options Integration

Register marketing-specific dropdown values:

```sql
-- Project types
INSERT INTO dropdown_options (dropdown_type, value, label, color, sort_order) VALUES
    ('mkt_project_type', 'campaign', 'Campaign', '#0d6efd', 1),
    ('mkt_project_type', 'always_on', 'Always-On', '#198754', 2),
    ('mkt_project_type', 'event', 'Event', '#fd7e14', 3),
    ('mkt_project_type', 'launch', 'Product Launch', '#6f42c1', 4),
    ('mkt_project_type', 'branding', 'Branding', '#d63384', 5),
    ('mkt_project_type', 'research', 'Research', '#6c757d', 6);

-- Channels
INSERT INTO dropdown_options (dropdown_type, value, label, color, sort_order) VALUES
    ('mkt_channel', 'meta_ads', 'Meta Ads', '#1877F2', 1),
    ('mkt_channel', 'google_ads', 'Google Ads', '#4285F4', 2),
    ('mkt_channel', 'radio', 'Radio', '#FF6B35', 3),
    ('mkt_channel', 'print', 'Print', '#2D3436', 4),
    ('mkt_channel', 'ooh', 'OOH / Outdoor', '#00B894', 5),
    ('mkt_channel', 'influencer', 'Influencer', '#E84393', 6),
    ('mkt_channel', 'email', 'Email Marketing', '#FDCB6E', 7),
    ('mkt_channel', 'sms', 'SMS', '#636E72', 8),
    ('mkt_channel', 'events', 'Events', '#6C5CE7', 9),
    ('mkt_channel', 'other', 'Other', '#95A5A6', 10);

-- Project statuses
INSERT INTO dropdown_options (dropdown_type, value, label, color, sort_order) VALUES
    ('mkt_project_status', 'draft', 'Draft', '#6c757d', 1),
    ('mkt_project_status', 'pending_approval', 'Pending Approval', '#ffc107', 2),
    ('mkt_project_status', 'approved', 'Approved', '#198754', 3),
    ('mkt_project_status', 'active', 'Active', '#0d6efd', 4),
    ('mkt_project_status', 'paused', 'Paused', '#fd7e14', 5),
    ('mkt_project_status', 'completed', 'Completed', '#20c997', 6),
    ('mkt_project_status', 'cancelled', 'Cancelled', '#dc3545', 7),
    ('mkt_project_status', 'archived', 'Archived', '#adb5bd', 8);

-- KPI status
INSERT INTO dropdown_options (dropdown_type, value, label, color, sort_order) VALUES
    ('mkt_kpi_status', 'no_data', 'No Data', '#6c757d', 1),
    ('mkt_kpi_status', 'exceeded', 'Exceeded', '#198754', 2),
    ('mkt_kpi_status', 'on_track', 'On Track', '#0d6efd', 3),
    ('mkt_kpi_status', 'at_risk', 'At Risk', '#ffc107', 4),
    ('mkt_kpi_status', 'behind', 'Behind', '#dc3545', 5);
```

### 5. Permissions V2 Integration

Register marketing module permissions:

```sql
INSERT INTO permissions_v2 (module_key, module_label, module_icon, entity_key, entity_label, action_key, action_label, description, is_scope_based, sort_order) VALUES
    ('marketing', 'Marketing', 'bi-megaphone', 'project', 'Projects', 'view', 'View', 'View marketing projects', true, 1),
    ('marketing', 'Marketing', 'bi-megaphone', 'project', 'Projects', 'create', 'Create', 'Create marketing projects', true, 2),
    ('marketing', 'Marketing', 'bi-megaphone', 'project', 'Projects', 'edit', 'Edit', 'Edit marketing projects', true, 3),
    ('marketing', 'Marketing', 'bi-megaphone', 'project', 'Projects', 'delete', 'Delete', 'Delete marketing projects', true, 4),
    ('marketing', 'Marketing', 'bi-megaphone', 'project', 'Projects', 'approve', 'Submit for Approval', 'Submit projects for approval', true, 5),
    ('marketing', 'Marketing', 'bi-megaphone', 'budget', 'Budgets', 'view', 'View', 'View budget allocations', true, 6),
    ('marketing', 'Marketing', 'bi-megaphone', 'budget', 'Budgets', 'edit', 'Edit', 'Edit budgets and record spend', true, 7),
    ('marketing', 'Marketing', 'bi-megaphone', 'kpi', 'KPIs', 'view', 'View', 'View KPI targets and actuals', true, 8),
    ('marketing', 'Marketing', 'bi-megaphone', 'kpi', 'KPIs', 'edit', 'Edit', 'Set KPI targets and record values', true, 9),
    ('marketing', 'Marketing', 'bi-megaphone', 'report', 'Reports', 'view', 'View', 'View marketing reports', true, 10);
```

Scope-based access means:
- `deny` → no access
- `own` → only projects where user is owner or member
- `department` → projects in user's department
- `all` → all projects

### 6. Module Menu Integration

```sql
-- Parent menu item
INSERT INTO module_menu_items (module_key, name, description, icon, url, color, status, sort_order)
VALUES ('marketing', 'Marketing', 'Marketing project management', 'bi-megaphone', '/marketing', '#E84393', 'active', 50);

-- Sub-items
INSERT INTO module_menu_items (parent_id, module_key, name, icon, url, sort_order)
VALUES 
    ((SELECT id FROM module_menu_items WHERE module_key = 'marketing' AND parent_id IS NULL), 'marketing', 'Projects', 'bi-kanban', '/marketing/projects', 1),
    ((SELECT id FROM module_menu_items WHERE module_key = 'marketing' AND parent_id IS NULL), 'marketing', 'Budget Overview', 'bi-wallet2', '/marketing/budgets', 2),
    ((SELECT id FROM module_menu_items WHERE module_key = 'marketing' AND parent_id IS NULL), 'marketing', 'KPI Dashboard', 'bi-speedometer2', '/marketing/kpis', 3),
    ((SELECT id FROM module_menu_items WHERE module_key = 'marketing' AND parent_id IS NULL), 'marketing', 'Reports', 'bi-graph-up', '/marketing/reports', 4);
```

---

## KPI Seed Data

```sql
INSERT INTO mkt_kpi_definitions (name, slug, unit, direction, category, formula, sort_order) VALUES
    ('Cost Per Acquisition', 'cpa', 'currency', 'lower', 'performance', 'spent / conversions', 1),
    ('Return On Ad Spend', 'roas', 'ratio', 'higher', 'financial', 'revenue / spent', 2),
    ('Cost Per Lead', 'cpl', 'currency', 'lower', 'performance', 'spent / leads', 3),
    ('Click-Through Rate', 'ctr', 'percentage', 'higher', 'engagement', 'clicks / impressions * 100', 4),
    ('Conversion Rate', 'cvr', 'percentage', 'higher', 'conversion', 'conversions / clicks * 100', 5),
    ('Cost Per Click', 'cpc', 'currency', 'lower', 'performance', 'spent / clicks', 6),
    ('Cost Per Mille', 'cpm', 'currency', 'lower', 'performance', 'spent / impressions * 1000', 7),
    ('Impressions', 'impressions', 'number', 'higher', 'brand', NULL, 8),
    ('Reach', 'reach', 'number', 'higher', 'brand', NULL, 9),
    ('Leads Generated', 'leads', 'number', 'higher', 'conversion', NULL, 10),
    ('Sales / Conversions', 'conversions', 'number', 'higher', 'conversion', NULL, 11),
    ('Revenue Generated', 'revenue', 'currency', 'higher', 'financial', NULL, 12),
    ('Total Spend', 'total_spend', 'currency', 'lower', 'financial', NULL, 13),
    ('Video Views', 'video_views', 'number', 'higher', 'engagement', NULL, 14),
    ('Engagement Rate', 'engagement_rate', 'percentage', 'higher', 'engagement', '(likes + comments + shares) / impressions * 100', 15);
```

---

## Flask API Routes

```
Blueprint: marketing_bp, prefix=/api/v1/marketing

# --- Projects ---
GET    /projects                          # List (filterable: status, brand, company, owner, date range)
POST   /projects                          # Create
GET    /projects/<id>                     # Detail with budget lines, KPIs, members, recent activity
PUT    /projects/<id>                     # Update
DELETE /projects/<id>                     # Soft delete (set deleted_at)
POST   /projects/<id>/submit-approval     # Submit to approval engine
POST   /projects/<id>/activate            # Move approved → active
POST   /projects/<id>/pause               # Pause active project
POST   /projects/<id>/complete            # Mark complete
POST   /projects/<id>/duplicate           # Clone project as new draft

# --- Members ---
GET    /projects/<id>/members
POST   /projects/<id>/members
PUT    /projects/<id>/members/<member_id>
DELETE /projects/<id>/members/<member_id>

# --- Budget Lines ---
GET    /projects/<id>/budget-lines
POST   /projects/<id>/budget-lines
PUT    /projects/<id>/budget-lines/<line_id>
DELETE /projects/<id>/budget-lines/<line_id>

# --- Budget Transactions ---
GET    /budget-lines/<line_id>/transactions
POST   /budget-lines/<line_id>/transactions
DELETE /budget-transactions/<tx_id>

# --- KPIs ---
GET    /projects/<id>/kpis
POST   /projects/<id>/kpis
PUT    /projects/<id>/kpis/<kpi_id>
DELETE /projects/<id>/kpis/<kpi_id>
POST   /projects/<id>/kpis/<kpi_id>/snapshot   # Record a KPI value

# --- Comments ---
GET    /projects/<id>/comments
POST   /projects/<id>/comments
PUT    /comments/<comment_id>
DELETE /comments/<comment_id>

# --- Files ---
GET    /projects/<id>/files
POST   /projects/<id>/files
DELETE /files/<file_id>

# --- Activity ---
GET    /projects/<id>/activity              # Paginated activity feed

# --- KPI Definitions (Admin) ---
GET    /kpi-definitions
POST   /kpi-definitions
PUT    /kpi-definitions/<id>

# --- Dashboard / Reports ---
GET    /dashboard/summary                  # Active projects count, total budget, alerts
GET    /dashboard/budget-overview          # Cross-project: planned vs spent by channel
GET    /dashboard/kpi-scoreboard           # All active projects KPI health
GET    /reports/budget-vs-actual            # Per project or aggregated
GET    /reports/channel-performance         # ROI by channel across projects
```

---

## React Frontend Pages

### /marketing/projects (Project List)
- Card grid or table view (toggle)
- Filter bar: status, brand, company, date range, owner, tags
- Sort: created_at, budget, start_date, name
- Quick-status badges with dropdown_options colors
- Budget burn rate indicator per card
- "New Project" button

### /marketing/projects/:id (Project Detail)
- Tabs: Overview, Budget, KPIs, Team, Activity, Files, Comments
- **Overview tab:** Status badge, dates, objective, brief, channel mix chips, approval status widget (EntityApprovalWidget), action buttons (Submit, Activate, Pause, Complete)
- **Budget tab:** Budget lines table with channel, planned/approved/spent, bar chart. Add budget line form. Spend recording. Budget utilization donut chart.
- **KPIs tab:** KPI cards with traffic-light status (red/yellow/green). Target vs actual with progress bar. Sparkline chart from snapshots. Add/edit KPI targets.
- **Team tab:** Member list with role badges. Add member autocomplete. Remove member.
- **Activity tab:** Chronological feed (decisions, status changes, budget modifications, comments).
- **Files tab:** File list with type icons. Upload area. Drive link paste.
- **Comments tab:** Threaded comments with reply. Internal note toggle.

### /marketing/budgets (Budget Command Center)
- Cross-project budget overview
- Planned vs Approved vs Spent stacked bars
- By channel breakdown
- By brand/company breakdown
- Budget utilization heat map
- Alerts: overspend, underspend, unallocated

### /marketing/kpis (KPI Scoreboard)
- All active projects in rows
- KPIs as columns
- Cell = traffic light with value
- Click cell → detail drawer with snapshot chart
- Filter by brand, status, channel

### /marketing/reports
- Budget vs Actual report (exportable)
- Channel Performance comparison
- Time-series trends
- Project completion rate

---

## Implementation Order

**Phase 1 — Core CRUD (get data in):**
1. Run all CREATE TABLE migrations
2. Seed dropdown_options, kpi_definitions, permissions_v2, module_menu_items
3. mkt_projects CRUD routes + basic list/detail frontend
4. Budget lines CRUD
5. Project members CRUD
6. Activity logging on every mutation

**Phase 2 — Intelligence (make it useful):**
1. Wire approval engine integration (submit, event handlers)
2. KPI targets and snapshot recording
3. Budget transactions / spend tracking
4. Comments and files
5. Project detail page with all tabs

**Phase 3 — Visibility (decision support):**
1. Budget Command Center dashboard
2. KPI Scoreboard
3. Cross-project reports
4. Tag-based filtering
5. Notification triggers (KPI alerts, budget warnings)

**Phase 4 — Automation:**
1. Ad platform API sync (Meta, Google → auto budget transactions)
2. KPI auto-calculation from transaction data
3. Invoice linking (mkt_budget_transactions → invoices table)
4. Scheduled KPI status recomputation
