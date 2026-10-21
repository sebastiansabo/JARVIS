import { api } from './client'
import type {
  SaleDocType,
  SaleDocForm,
  LeasingCompany,
  LeasingCompanyCreate,
  DispoDocument,
} from '../types/carpark'

export const carparkSaleDocsApi = {
  // Renders a sale document (contract / proforma / garantie) and streams
  // the PDF bytes back — nothing is persisted server-side. Routed through a
  // raw fetch (not `api.post`): the shared client always calls
  // response.json() on the body and can't return a Blob.
  generate: async (
    vehicleId: number,
    body: { doc_type: SaleDocType; form: SaleDocForm },
  ): Promise<Blob> => {
    const res = await fetch(`/api/carpark/vehicles/${vehicleId}/sale-documents/generate`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify(body),
    })
    if (!res.ok) {
      let msg = `Eroare ${res.status}`
      try {
        const d = await res.json()
        if (d && d.error) msg = String(d.error)
      } catch {
        /* non-JSON error body */
      }
      throw new Error(msg)
    }
    return res.blob()
  },

  // Renders, uploads to Drive, and records the result as a vehicle
  // document (carpark_vehicle_documents row).
  save: (vehicleId: number, body: { doc_type: SaleDocType; form: SaleDocForm }) =>
    api.post<{ document: DispoDocument }>(
      `/api/carpark/vehicles/${vehicleId}/sale-documents/save`,
      body,
    ),

  // Global leasing-companies directory, for the sale form's "Cumpărător" picker.
  listLeasingCompanies: () =>
    api.get<{ leasing_companies: LeasingCompany[] }>('/api/carpark/leasing-companies'),

  createLeasingCompany: (body: LeasingCompanyCreate) =>
    api.post<{ leasing_company: LeasingCompany }>('/api/carpark/leasing-companies', body),
}
