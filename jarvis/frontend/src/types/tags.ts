export interface TagGroup {
  id: number
  name: string
  description: string | null
  color: string | null
  sort_order: number
  is_active: boolean
}

export interface Tag {
  id: number
  name: string
  group_id: number | null
  group_name?: string
  group_color?: string
  color: string | null
  icon: string | null
  sort_order: number
  is_global: boolean
  is_active: boolean
  created_by?: number
}

export interface RuleCondition {
  field: string
  operator: string
  value: string
}

export interface AutoTagRule {
  id: number
  name: string
  entity_type: string
  tag_id: number
  tag_name?: string
  tag_color?: string
  conditions: RuleCondition[]
  match_mode?: 'all' | 'any'
  is_active: boolean
  run_on_create: boolean
  created_by?: number
  created_by_name?: string
  created_at?: string
}

export interface EntityTag {
  id: number
  name: string
  color: string | null
  group_name?: string
  group_color?: string
  tagged_by?: number
  created_at?: string
}
