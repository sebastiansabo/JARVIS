import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Switch } from '@/components/ui/switch'
import { Badge } from '@/components/ui/badge'
import {
  ChevronUp,
  ChevronDown,
  GripVertical,
  Save,
  Users,
  RotateCcw,
} from 'lucide-react'
import { settingsApi } from '@/api/settings'
import { toast } from 'sonner'
import type { DefaultColumnsMap } from '@/types/settings'

/* ── Column metadata per page ─────────────────────────────── */

interface ColumnMeta {
  key: string
  label: string
  locked?: boolean
}

const PAGE_COLUMNS: Record<string, { label: string; columns: ColumnMeta[] }> = {
  accounting: {
    label: 'Accounting',
    columns: [
      { key: 'supplier', label: 'Supplier' },
      { key: 'invoice_number', label: 'Invoice #' },
      { key: 'invoice_date', label: 'Date' },
      { key: 'net_value', label: 'Net Value', locked: true },
      { key: 'invoice_value', label: 'Total' },
      { key: 'company', label: 'Company' },
      { key: 'department', label: 'Department' },
      { key: 'status', label: 'Status' },
      { key: 'payment_status', label: 'Payment' },
      { key: 'drive_link', label: 'Drive Link' },
      { key: 'tags', label: 'Tags' },
    ],
  },
  crm_deals: {
    label: 'CRM — Sales',
    columns: [
      { key: 'source', label: 'Type', locked: true },
      { key: 'dossier_number', label: 'Dossier' },
      { key: 'brand', label: 'Brand' },
      { key: 'model_name', label: 'Model' },
      { key: 'buyer_name', label: 'Client' },
      { key: 'dossier_status', label: 'Status' },
      { key: 'sale_price_net', label: 'Price' },
      { key: 'contract_date', label: 'Date' },
      { key: 'dealer_name', label: 'Dealer' },
      { key: 'branch', label: 'Branch' },
      { key: 'order_number', label: 'Order #' },
      { key: 'vin', label: 'VIN' },
      { key: 'engine_code', label: 'Engine' },
      { key: 'fuel_type', label: 'Fuel' },
      { key: 'color', label: 'Color' },
      { key: 'model_year', label: 'Year' },
      { key: 'order_status', label: 'Order Status' },
      { key: 'contract_status', label: 'Contract Status' },
      { key: 'sales_person', label: 'Sales Person' },
      { key: 'owner_name', label: 'Owner' },
      { key: 'list_price', label: 'List Price' },
      { key: 'purchase_price_net', label: 'Purchase Price' },
      { key: 'gross_profit', label: 'Gross Profit' },
      { key: 'discount_value', label: 'Discount' },
      { key: 'vehicle_type', label: 'Vehicle Type' },
      { key: 'registration_number', label: 'Reg. Number' },
      { key: 'delivery_date', label: 'Delivery' },
    ],
  },
  crm_clients: {
    label: 'CRM — Clients',
    columns: [
      { key: 'display_name', label: 'Name', locked: true },
      { key: 'nr_reg', label: 'Nr.Reg' },
      { key: 'client_type', label: 'Type' },
      { key: 'phone', label: 'Phone' },
      { key: 'email', label: 'Email' },
      { key: 'city', label: 'City' },
      { key: 'region', label: 'Region' },
      { key: 'responsible', label: 'Responsible' },
      { key: 'company_name', label: 'Company' },
      { key: 'street', label: 'Street' },
      { key: 'country', label: 'Country' },
      { key: 'client_since', label: 'Client Since' },
      { key: 'created_at', label: 'Created' },
    ],
  },
  dms: {
    label: 'DMS',
    columns: [
      { key: 'title', label: 'Title' },
      { key: 'category_name', label: 'Category' },
      { key: 'file_count', label: 'Files' },
      { key: 'children_count', label: 'Annexes' },
      { key: 'status', label: 'Status' },
      { key: 'expiry_date', label: 'Expiry' },
      { key: 'doc_number', label: 'Number' },
      { key: 'doc_date', label: 'Doc Date' },
      { key: 'company_name', label: 'Company' },
      { key: 'created_by_name', label: 'Created By' },
      { key: 'created_at', label: 'Date' },
    ],
  },
  marketing: {
    label: 'Marketing',
    columns: [
      { key: 'name', label: 'Project' },
      { key: 'company_name', label: 'Company' },
      { key: 'brand_name', label: 'Brand' },
      { key: 'project_type', label: 'Type' },
      { key: 'status', label: 'Status' },
      { key: 'total_budget', label: 'Budget' },
      { key: 'total_spent', label: 'Spent' },
      { key: 'owner_name', label: 'Owner' },
      { key: 'start_date', label: 'Start Date' },
      { key: 'end_date', label: 'End Date' },
    ],
  },
  efactura: {
    label: 'e-Factura',
    columns: [
      { key: 'supplier', label: 'Supplier' },
      { key: 'invoice_number', label: 'Invoice #' },
      { key: 'date', label: 'Date' },
      { key: 'due_date', label: 'Due Date' },
      { key: 'direction', label: 'Direction' },
      { key: 'amount', label: 'Amount' },
      { key: 'vat', label: 'VAT' },
      { key: 'without_vat', label: 'Without VAT' },
      { key: 'company', label: 'Company' },
      { key: 'type', label: 'Type' },
      { key: 'department', label: 'Department' },
      { key: 'subdepartment', label: 'Subdepartment' },
      { key: 'mapped_supplier', label: 'Mapped Supplier' },
      { key: 'mapped_brand', label: 'Brand' },
      { key: 'kod_konto', label: 'Kod Konto' },
    ],
  },
}

const PAGE_IDS = Object.keys(PAGE_COLUMNS)

export default function TablesTab() {
  const qc = useQueryClient()
  const [selectedPage, setSelectedPage] = useState(PAGE_IDS[0])
  const pageMeta = PAGE_COLUMNS[selectedPage]

  const { data: serverDefaults } = useQuery<DefaultColumnsMap>({
    queryKey: ['default-columns'],
    queryFn: settingsApi.getDefaultColumns,
  })

  // Current server-saved columns for selected page
  const serverCols = serverDefaults?.[selectedPage]?.columns ?? null
  const serverVersion = serverDefaults?.[selectedPage]?.version ?? 0

  // Local working state — initialised from server or all columns visible
  const [columns, setColumns] = useState<string[]>([])
  const [initialized, setInitialized] = useState<string | null>(null)

  // Re-initialise when page changes or server data arrives
  if (initialized !== selectedPage && pageMeta) {
    const initial = serverCols ?? pageMeta.columns.map((c) => c.key)
    setColumns(initial)
    setInitialized(selectedPage)
  }

  const allKeys = useMemo(() => pageMeta.columns.map((c) => c.key), [pageMeta])
  const colMap = useMemo(
    () => new Map(pageMeta.columns.map((c) => [c.key, c])),
    [pageMeta],
  )

  const visibleCols = columns.filter((k) => allKeys.includes(k))
  const hiddenCols = pageMeta.columns.filter(
    (c) => !visibleCols.includes(c.key) && !c.locked,
  )

  // Check if current state differs from server
  const isDirty = useMemo(() => {
    if (!serverCols) return columns.length > 0
    if (columns.length !== serverCols.length) return true
    return columns.some((k, i) => k !== serverCols[i])
  }, [columns, serverCols])

  const moveUp = (idx: number) => {
    if (idx <= 0) return
    const next = [...columns]
    ;[next[idx - 1], next[idx]] = [next[idx], next[idx - 1]]
    setColumns(next)
  }

  const moveDown = (idx: number) => {
    if (idx >= columns.length - 1) return
    const next = [...columns]
    ;[next[idx], next[idx + 1]] = [next[idx + 1], next[idx]]
    setColumns(next)
  }

  const toggleColumn = (key: string) => {
    const meta = colMap.get(key)
    if (meta?.locked) return
    if (columns.includes(key)) {
      setColumns(columns.filter((k) => k !== key))
    } else {
      setColumns([...columns, key])
    }
  }

  const resetToAll = () => {
    setColumns(pageMeta.columns.map((c) => c.key))
  }

  const saveMutation = useMutation({
    mutationFn: (applyToAll: boolean) =>
      settingsApi.setDefaultColumns({
        page: selectedPage,
        columns,
        apply_to_all: applyToAll,
      }),
    onSuccess: (_, applyToAll) => {
      qc.invalidateQueries({ queryKey: ['default-columns'] })
      toast.success(
        applyToAll
          ? 'Defaults applied to all users'
          : 'Defaults saved for new users',
      )
    },
    onError: () => toast.error('Failed to save defaults'),
  })

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Default Table Columns</CardTitle>
          <p className="text-sm text-muted-foreground">
            Configure the default column visibility and order for each module.
            Users can still customise their own view.
          </p>
        </CardHeader>
        <CardContent className="space-y-4">
          {/* Page selector */}
          <div className="flex items-center gap-3">
            <Select value={selectedPage} onValueChange={(v) => { setSelectedPage(v); setInitialized(null) }}>
              <SelectTrigger className="w-48">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {PAGE_IDS.map((id) => (
                  <SelectItem key={id} value={id}>
                    {PAGE_COLUMNS[id].label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            {serverCols && (
              <Badge variant="outline" className="text-xs">
                v{serverVersion}
              </Badge>
            )}
          </div>

          {/* Visible columns */}
          <div className="rounded-md border">
            <div className="border-b bg-muted/50 px-3 py-2">
              <p className="text-xs font-medium text-muted-foreground">
                Visible columns ({visibleCols.length})
              </p>
            </div>
            <div className="max-h-[360px] overflow-y-auto divide-y">
              {visibleCols.map((key, idx) => {
                const meta = colMap.get(key)
                if (!meta) return null
                return (
                  <div
                    key={key}
                    className="flex items-center gap-2 px-3 py-1.5 hover:bg-accent/50"
                  >
                    <GripVertical className="h-3.5 w-3.5 shrink-0 text-muted-foreground/50" />
                    <span className="flex-1 text-sm">{meta.label}</span>
                    {meta.locked && (
                      <Badge variant="secondary" className="text-[10px] px-1.5 py-0">
                        locked
                      </Badge>
                    )}
                    <button
                      onClick={() => moveUp(idx)}
                      disabled={idx === 0}
                      className="rounded p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-25"
                    >
                      <ChevronUp className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => moveDown(idx)}
                      disabled={idx === visibleCols.length - 1}
                      className="rounded p-0.5 text-muted-foreground hover:text-foreground disabled:opacity-25"
                    >
                      <ChevronDown className="h-3.5 w-3.5" />
                    </button>
                    {!meta.locked && (
                      <Switch
                        checked
                        onCheckedChange={() => toggleColumn(key)}
                        className="h-4 w-7 [&>span]:h-3 [&>span]:w-3"
                      />
                    )}
                  </div>
                )
              })}
            </div>
          </div>

          {/* Hidden columns */}
          {hiddenCols.length > 0 && (
            <div className="rounded-md border">
              <div className="border-b bg-muted/50 px-3 py-2">
                <p className="text-xs font-medium text-muted-foreground">
                  Hidden columns ({hiddenCols.length})
                </p>
              </div>
              <div className="max-h-[200px] overflow-y-auto divide-y">
                {hiddenCols.map((meta) => (
                  <div
                    key={meta.key}
                    className="flex items-center gap-2 px-3 py-1.5 hover:bg-accent/50"
                  >
                    <span className="flex-1 text-sm text-muted-foreground">
                      {meta.label}
                    </span>
                    <Switch
                      checked={false}
                      onCheckedChange={() => toggleColumn(meta.key)}
                      className="h-4 w-7 [&>span]:h-3 [&>span]:w-3"
                    />
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Actions */}
          <div className="flex items-center gap-2 pt-2">
            <Button
              size="sm"
              variant="outline"
              onClick={() => saveMutation.mutate(false)}
              disabled={!isDirty || saveMutation.isPending}
            >
              <Save className="mr-1.5 h-3.5 w-3.5" />
              Save as Default
            </Button>
            <Button
              size="sm"
              onClick={() => saveMutation.mutate(true)}
              disabled={!isDirty || saveMutation.isPending}
            >
              <Users className="mr-1.5 h-3.5 w-3.5" />
              Apply to All Users
            </Button>
            <Button
              size="sm"
              variant="ghost"
              onClick={resetToAll}
              className="ml-auto"
            >
              <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
              Show All
            </Button>
          </div>

          <p className="text-xs text-muted-foreground">
            <strong>Save as Default</strong> — new users (without local
            customisations) will see this layout.{' '}
            <strong>Apply to All Users</strong> — resets every user's columns to
            this layout on their next page load.
          </p>
        </CardContent>
      </Card>
    </div>
  )
}
