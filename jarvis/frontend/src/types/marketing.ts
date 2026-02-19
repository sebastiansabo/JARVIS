// Marketing Projects Module — TypeScript types

export interface MktProject {
  id: number
  name: string
  slug: string
  description: string | null
  company_id: number
  company_ids: number[]
  company_name: string | null
  brand_id: number | null
  brand_ids: number[]
  brand_name: string | null
  department_structure_id: number | null
  department_ids: number[]
  project_type: string
  channel_mix: string[]
  status: MktProjectStatus
  start_date: string | null
  end_date: string | null
  total_budget: number
  currency: string
  owner_id: number
  owner_name: string | null
  owner_email: string | null
  created_by: number
  created_by_name: string | null
  objective: string | null
  target_audience: string | null
  brief: Record<string, unknown>
  approval_mode: 'any' | 'all'
  external_ref: string | null
  metadata: Record<string, unknown>
  created_at: string
  updated_at: string | null
  deleted_at: string | null
  // Computed
  total_spent?: number
  event_cost?: number
  // Nested (from detail endpoint)
  members?: MktMember[]
  budget_lines?: MktBudgetLine[]
  activity?: MktActivity[]
}

export type MktProjectStatus =
  | 'draft'
  | 'pending_approval'
  | 'approved'
  | 'active'
  | 'paused'
  | 'completed'
  | 'archived'
  | 'cancelled'

export interface MktMember {
  id: number
  project_id: number
  user_id: number
  user_name: string | null
  user_email: string | null
  role: 'owner' | 'manager' | 'specialist' | 'viewer' | 'agency' | 'stakeholder' | 'observer'
  department_structure_id: number | null
  added_by: number
  added_by_name: string | null
  created_at: string
}

export interface MktBudgetLine {
  id: number
  project_id: number
  channel: string
  description: string | null
  department_structure_id: number | null
  agency_name: string | null
  planned_amount: number
  approved_amount: number
  spent_amount: number
  currency: string
  period_type: string
  period_start: string | null
  period_end: string | null
  status: string
  notes: string | null
  created_at: string
  updated_at: string | null
  // Computed
  computed_spent?: number
}

export interface MktBudgetTransaction {
  id: number
  budget_line_id: number
  amount: number
  direction: 'debit' | 'credit'
  source: string
  reference_id: string | null
  invoice_id: number | null
  invoice_supplier: string | null
  invoice_number_ref: string | null
  transaction_date: string
  description: string | null
  recorded_by: number
  recorded_by_name: string | null
  created_at: string
}

export interface KpiBenchmarkSegment {
  name: string
  average: number
  good: number
  excellent: number
  source: string
}

export interface KpiBenchmarks {
  industry: string
  generated_at: string
  segments: KpiBenchmarkSegment[]
}

export interface MktKpiDefinition {
  id: number
  name: string
  slug: string
  unit: 'number' | 'currency' | 'percentage' | 'ratio'
  direction: 'higher' | 'lower'
  category: string
  formula: string | null
  variables: string[]
  description: string | null
  benchmarks: KpiBenchmarks | null
  is_active: boolean
  sort_order: number
  created_at: string
}

export interface MktProjectKpi {
  id: number
  project_id: number
  kpi_definition_id: number
  kpi_name: string | null
  kpi_slug: string | null
  unit: string | null
  direction: string | null
  category: string | null
  formula: string | null
  channel: string | null
  target_value: number | null
  current_value: number | null
  weight: number
  threshold_warning: number | null
  threshold_critical: number | null
  currency: string | null
  status: 'no_data' | 'on_track' | 'at_risk' | 'behind' | 'exceeded'
  last_synced_at: string | null
  notes: string | null
  show_on_overview: boolean
  created_at: string
  updated_at: string | null
}

export interface MktKpiSnapshot {
  id: number
  project_kpi_id: number
  value: number
  source: string
  recorded_at: string
  recorded_by: number | null
  recorded_by_name: string | null
  notes: string | null
}

export interface MktActivity {
  id: number
  project_id: number
  action: string
  actor_id: number | null
  actor_name: string | null
  actor_type: string
  details: Record<string, unknown>
  created_at: string
}

export interface MktComment {
  id: number
  project_id: number
  parent_id: number | null
  user_id: number
  user_name: string | null
  user_email: string | null
  content: string
  is_internal: boolean
  created_at: string
  updated_at: string | null
  deleted_at: string | null
}

export interface MktFile {
  id: number
  project_id: number
  file_name: string
  file_type: string | null
  mime_type: string | null
  file_size: number | null
  storage_uri: string
  uploaded_by: number
  uploaded_by_name: string | null
  description: string | null
  created_at: string
}

export interface MktProjectFilters {
  status?: string
  company_id?: number
  brand_id?: number
  owner_id?: number
  project_type?: string
  date_from?: string
  date_to?: string
  search?: string
  limit?: number
  offset?: number
}

export interface MktDashboardSummary {
  active_count: number
  draft_count: number
  pending_count: number
  completed_count: number
  total_count: number
  total_active_budget: number
  total_active_spent: number
  total_budget: number
  total_spent: number
  kpi_alerts: number
}

export interface MktBudgetOverviewChannel {
  channel: string
  planned: number
  approved: number
  spent: number
  project_count: number
}

export interface MktKpiScoreboardItem {
  project_id: number
  project_name: string
  kpi_id: number
  kpi_name: string
  slug: string
  unit: string
  direction: string
  target_value: number | null
  current_value: number | null
  status: string
  channel: string | null
}

export interface MktProjectEvent {
  id: number
  project_id: number
  event_id: number
  notes: string | null
  linked_by: number
  linked_by_name: string | null
  created_at: string
  event_name: string
  event_start_date: string
  event_end_date: string
  event_company: string | null
  event_brand: string | null
  event_description: string | null
  event_cost: number
}

export interface HrEventSearchResult {
  id: number
  name: string
  start_date: string
  end_date: string
  company: string | null
  brand: string | null
  description: string | null
}

export interface MktKpiBudgetLine {
  id: number
  project_kpi_id: number
  budget_line_id: number
  role: string
  channel: string
  description: string | null
  planned_amount: number
  spent_amount: number
  currency: string
  created_at: string
}

export interface MktKpiDependency {
  id: number
  project_kpi_id: number
  depends_on_kpi_id: number
  role: string
  dep_current_value: number | null
  dep_kpi_name: string
  dep_kpi_slug: string
  dep_unit: string
  created_at: string
}

// ── OKR ──

export interface MktObjective {
  id: number
  project_id: number
  title: string
  description: string | null
  sort_order: number
  created_by: number
  created_at: string
  updated_at: string | null
  progress: number
  key_results: MktKeyResult[]
}

export interface MktKeyResult {
  id: number
  objective_id: number
  title: string
  target_value: number
  current_value: number
  unit: string
  linked_kpi_id: number | null
  linked_kpi_name: string | null
  sort_order: number
  created_at: string
  updated_at: string | null
  progress: number
}

export interface InvoiceSearchResult {
  id: number
  supplier: string
  invoice_number: string
  invoice_date: string
  invoice_value: number
  currency: string
  status: string
  payment_status: string
}

// ── Campaign Simulator ──

export interface SimBenchmark {
  id: number
  channel_key: string
  channel_label: string
  funnel_stage: 'awareness' | 'consideration' | 'conversion'
  month_index: number
  cpc: number
  cvr_lead: number
  cvr_car: number
  is_active: boolean
}

export interface SimChannelResult {
  channel_key: string
  channel_label: string
  funnel_stage: string
  month_index: number
  budget: number
  cpc: number
  clicks: number
  cvr_lead: number
  leads: number
  cvr_car: number
  cars: number
}

export interface SimStageTotal {
  budget: number
  clicks: number
  leads: number
}

export interface SimTotals {
  total_budget: number
  total_clicks: number
  total_leads: number
  cost_per_lead: number
  total_cars: number
  cost_per_car: number
}

export interface SimSettings {
  awareness_threshold: number
  awareness_multiplier: number
  consideration_threshold: number
  consideration_multiplier: number
  auto_month_pcts: [number, number, number]
  auto_stage_weights: [
    { awareness: number; consideration: number; conversion: number },
    { awareness: number; consideration: number; conversion: number },
    { awareness: number; consideration: number; conversion: number },
  ]
  default_active: Record<string, string[]>
}
