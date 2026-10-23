export type RecordStatusKey =
  | 'pending_evaluation'
  | 'initial_offer'
  | 'inspection'
  | 'final_offer'
  | 'consignment_offer'
  | 'bought'
  | 'consignat'
  | 'lost'
  | 'cancelled'
  | 'on_hold'
  | 'unknown'

export function recordStatus(status: string): {
  key: RecordStatusKey
  label: string
  badgeClass: string
  rowClass: string
} {
  switch (status) {
    case 'PENDING_EVALUATION':
      return {
        key: 'pending_evaluation',
        label: 'În evaluare',
        badgeClass: 'bg-amber-500 text-white',
        rowClass: 'bg-amber-500/5 border-l-4 border-l-amber-500/40',
      }
    case 'INITIAL_OFFER':
      return {
        key: 'initial_offer',
        label: 'Ofertă',
        badgeClass: 'bg-blue-600 text-white',
        rowClass: 'bg-blue-500/5 border-l-4 border-l-blue-500/40',
      }
    case 'INSPECTION':
      return {
        key: 'inspection',
        label: 'În inspecție',
        badgeClass: 'bg-purple-600 text-white',
        rowClass: 'bg-purple-500/5 border-l-4 border-l-purple-500/40',
      }
    case 'FINAL_OFFER':
      return {
        key: 'final_offer',
        label: 'Ofertă finală',
        badgeClass: 'bg-indigo-600 text-white',
        rowClass: 'bg-indigo-500/5 border-l-4 border-l-indigo-500/40',
      }
    case 'CONSIGNMENT_OFFER':
      return {
        key: 'consignment_offer',
        label: 'Ofertă consignație',
        badgeClass: 'bg-teal-600 text-white',
        rowClass: 'bg-teal-500/5 border-l-4 border-l-teal-500/40',
      }
    case 'BOUGHT':
      return {
        key: 'bought',
        label: 'Achiziționat',
        badgeClass: 'bg-green-600 text-white',
        rowClass: 'bg-green-500/5 border-l-4 border-l-green-500/40',
      }
    case 'CONSIGNAT':
      return {
        key: 'consignat',
        label: 'Consignat',
        badgeClass: 'bg-teal-700 text-white',
        rowClass: 'bg-teal-500/5 border-l-4 border-l-teal-600/40',
      }
    case 'LOST':
      return {
        key: 'lost',
        label: 'Pierdut',
        badgeClass: 'bg-slate-600 text-white',
        rowClass: 'bg-slate-500/5 border-l-4 border-l-slate-500/40',
      }
    case 'CANCELLED':
      return {
        key: 'cancelled',
        label: 'Anulat',
        badgeClass: 'bg-gray-600 text-white',
        rowClass: 'bg-gray-500/5 border-l-4 border-l-gray-500/40',
      }
    case 'ON_HOLD':
      return {
        key: 'on_hold',
        label: 'Suspendat',
        badgeClass: 'bg-amber-600 text-white',
        rowClass: 'bg-amber-500/5 border-l-4 border-l-amber-500/40',
      }
    default:
      return {
        key: 'unknown',
        label: 'Necunoscut',
        badgeClass: 'bg-gray-600 text-white',
        rowClass: 'bg-gray-500/5 border-l-4 border-l-gray-500/40',
      }
  }
}

export const STATUS_FILTER_OPTIONS = [
  { value: 'PENDING_EVALUATION', label: 'În evaluare' },
  { value: 'INITIAL_OFFER', label: 'Ofertă' },
  { value: 'INSPECTION', label: 'În inspecție' },
  { value: 'FINAL_OFFER', label: 'Ofertă finală' },
  { value: 'CONSIGNMENT_OFFER', label: 'Ofertă consignație' },
  { value: 'BOUGHT', label: 'Achiziționat' },
  { value: 'CONSIGNAT', label: 'Consignat' },
  { value: 'LOST', label: 'Pierdut' },
  { value: 'CANCELLED', label: 'Anulat' },
  { value: 'ON_HOLD', label: 'Suspendat' },
]
