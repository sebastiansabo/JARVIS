export interface CheckinLocation {
  id: number
  name: string
  latitude: number
  longitude: number
  allowed_radius_meters: number
  auto_checkout_radius_meters: number
  allowed_ips: string[]
  is_active: boolean
  created_by: number | null
  created_at: string
  updated_at: string
}

export interface CheckinPunch {
  id: number
  biostar_event_id: string
  event_datetime: string
  direction: 'IN' | 'OUT'
  device_name: string
  raw_data: {
    source: string
    latitude: number
    longitude: number
    location_name: string
    distance_meters: number
  } | null
}

export interface CheckinStatus {
  mapped: boolean
  biostar_user_id?: string
  punches: CheckinPunch[]
  next_direction: 'IN' | 'OUT'
}

export interface PunchResult {
  success: boolean
  error?: string
  direction?: 'IN' | 'OUT'
  time?: string
  location?: string
  distance?: number
  allowed_radius?: number
  method?: 'gps_mobile' | 'ip_wifi' | 'qr_code'
}
