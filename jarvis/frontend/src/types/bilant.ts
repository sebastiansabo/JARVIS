// Bilant (Balance Sheet) Module — TypeScript types

export interface BilantTemplate {
  id: number
  name: string
  description: string | null
  company_id: number | null
  company_name: string | null
  is_default: boolean
  version: number
  created_by: number
  created_by_name: string | null
  row_count: number
  created_at: string
  updated_at: string | null
}

export interface BilantTemplateRow {
  id: number
  template_id: number
  description: string
  nr_rd: string | null
  formula_ct: string | null
  formula_rd: string | null
  row_type: 'data' | 'total' | 'section' | 'separator'
  is_bold: boolean
  indent_level: number
  sort_order: number
}

export type MetricGroup = 'summary' | 'ratio_input' | 'ratio' | 'structure' | 'derived'

export interface BilantMetricConfig {
  id: number
  template_id: number
  metric_key: string
  metric_label: string
  nr_rd: string | null
  metric_group: MetricGroup
  sort_order: number
  formula_expr: string | null
  display_format: 'currency' | 'ratio' | 'percent'
  interpretation: string | null
  threshold_good: number | null
  threshold_warning: number | null
  structure_side: 'assets' | 'liabilities' | null
}

export interface BilantGeneration {
  id: number
  template_id: number
  template_name: string | null
  company_id: number
  company_name: string | null
  period_label: string | null
  period_date: string | null
  status: 'processing' | 'completed' | 'error'
  error_message: string | null
  original_filename: string | null
  generated_by: number
  generated_by_name: string | null
  notes: string | null
  created_at: string
}

export interface BilantResult {
  id: number
  generation_id: number
  template_row_id: number | null
  nr_rd: string | null
  description: string
  formula_ct: string | null
  formula_rd: string | null
  value: number
  verification: string | null
  sort_order: number
  row_type: string
  is_bold: boolean
  indent_level: number
}

export interface BilantMetrics {
  summary: Record<string, number>
  ratios: Record<string, { value: number | null; label: string; interpretation?: string | null } | number | null>
  structure: {
    assets: { name: string; value: number; percent: number }[]
    liabilities: { name: string; value: number; percent: number }[]
  }
}

export interface BilantAiAnalysis {
  content: string
  model: string
  generated_at: string
  input_tokens: number
  output_tokens: number
}

export interface BilantGenerationDetail {
  generation: BilantGeneration
  results: BilantResult[]
  metrics: BilantMetrics
  metric_configs?: BilantMetricConfig[]
  ai_analysis?: BilantAiAnalysis | null
}

export interface ChartOfAccount {
  id: number
  code: string
  name: string
  account_class: number
  account_type: 'class' | 'group' | 'synthetic' | 'analytical'
  parent_code: string | null
  is_active: boolean
  company_id: number | null
  company_name: string | null
  created_at: string
  updated_at: string | null
}
