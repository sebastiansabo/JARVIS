export interface Company {
  id: number
  company: string
  vat: string | null
  created_at: string
}

export interface CompanyWithBrands extends Company {
  brands: string
  brands_list: { id: number; brand_id: number; brand: string }[]
  parent_company_id: number | null
  display_order: number
  logo_url: string | null
}

export interface Brand {
  id: number
  name: string
  is_active: boolean
}

export interface CompanyBrand {
  id: number
  company_id: number
  company: string
  brand: string
  brand_id: number
  is_active: boolean
  created_at: string
}

export interface Department {
  id: number
  company_id: number
  company: string
  department: string
  subdepartment: string | null
  manager: string | null
  manager_ids: number[] | null
  marketing: boolean
  is_active: boolean
  created_at: string
}

export interface DepartmentStructure {
  id: number
  company_id: number
  company: string
  brand: string | null
  department: string
  subdepartment: string | null
  manager: string | null
  marketing: boolean
  display_name: string
  unique_key: string
  responsable_id: number | null
  responsable_name: string | null
  responsable_email: string | null
  manager_ids: number[] | null
}

export interface StructureUnit {
  id: number
  company_id: number
  company: string
  brand: string | null
  department: string
  subdepartment: string | null
  manager: string | null
  marketing: boolean
  display_name: string
  unique_key: string
}

export interface StructureNode {
  id: number
  company_id: number
  parent_id: number | null
  name: string
  level: number
  has_team: boolean
  display_order: number
  created_at: string
}

export interface StructureNodeMember {
  id: number
  node_id: number
  user_id: number
  role: 'responsable' | 'team'
  user_name: string
  user_email: string
}
