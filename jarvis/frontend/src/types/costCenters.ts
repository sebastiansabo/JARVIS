export interface CostCenterCompany {
  company_id: number
  company: string
  count: number
}

export interface CostCenter {
  id: number
  company_id: number
  code: string
  name: string
  active: boolean
  display_order: number
  structure_node_id: number | null
  structure_node_name: string | null
}

export interface StructureNodeOption {
  id: number
  name: string
  level: number
}
