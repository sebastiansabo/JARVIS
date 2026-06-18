export interface BabPeriod {
  year: number
  month: number
  status: 'MISSING' | 'IMPORTED' | 'LOCKED'
  upload_id?: number
  import_count?: number
  filename?: string
  uploaded_at?: string
  marja_finala_eur?: number
}

export interface BabUpload {
  id: number
  company_id: number
  period_year: number
  period_month: number
  filename: string
  uploaded_by: number
  uploaded_at: string
  row_count: number
  status: string
  error_msg: string | null
  locked_at: string | null
  locked_by: number | null
  unlocked_at: string | null
  unlocked_by: number | null
  import_count: number
}

export interface MarjaLine {
  label: string
  lei: number
  eur: number
  accounts: number[]
  kst: number
}

export interface MarjaSection {
  section: string
  rows: MarjaLine[]
}

export interface MarjaReportData {
  sections: MarjaSection[]
  marja_finala_lei: number
  marja_finala_eur: number
  eur_rate: number
}

export interface BabEurRate {
  id: number
  company_id: number
  period_year: number
  period_month: number
  eur_rate: number
  set_by: number | null
  set_at: string
}
