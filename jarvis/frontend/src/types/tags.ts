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

export interface EntityTag {
  id: number
  tag_id: number
  name: string
  color: string | null
  group_name?: string
  group_color?: string
  tagged_by?: number
  created_at?: string
}
