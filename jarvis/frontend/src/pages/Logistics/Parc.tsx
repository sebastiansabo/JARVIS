import { useMemo } from 'react'
import { useQuery } from '@tanstack/react-query'
import { useNavigate, useSearchParams, useLocation } from 'react-router-dom'
import { ArrowUp, ArrowDown, ArrowUpDown } from 'lucide-react'

import { PageHeader } from '@/components/shared/PageHeader'
import { SearchInput } from '@/components/shared/SearchInput'
import { EmptyState } from '@/components/shared/EmptyState'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import {
  Table,
  TableHeader,
  TableBody,
  TableRow,
  TableHead,
  TableCell,
} from '@/components/ui/table'
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select'
import { cn } from '@/lib/utils'
import { logisticsApi, type ParcVehicleRow } from '@/api/logistics'
import {
  EMPTY_PARC_FILTERS,
  parseParcFiltersFromSearch,
  buildParcSearchParams,
  toListVehiclesFilters,
  nextSort,
  distinctLocationOptions,
  extractErrorMessage,
  type ParcFiltersState,
} from './Parc.helpers'

// Enumerations per docs/superpowers/specs/2026-11-27-jarvis-parc-design.md §3.
// Static (no admin CRUD yet) -- kept here rather than fetched.
const DESTINATIE_OPTIONS = ['Intern', 'AAP', 'Export', 'Expunere']
const ETAPA_OPTIONS = ['În tranzit', 'În pregătire', 'În stoc', 'Expunere']
const PREDARE_OPTIONS = ['În așteptare', 'Pregătit de predare', 'Blocat', 'Predat']

// Display order + exact RO headers per the brief/spec §4.1. `sortKey` must
// match a key in vehicle_repository.py's _VEHICLE_SORT_COLUMNS whitelist.
const COLUMNS: { key: keyof ParcVehicleRow; label: string; sortKey: string }[] = [
  { key: 'vehicul', label: 'Vehicul', sortKey: 'vehicul' },
  { key: 'comanda', label: 'Comandă', sortKey: 'comanda' },
  { key: 'locatie', label: 'Locație', sortKey: 'locatie' },
  { key: 'pozitie', label: 'Poziție', sortKey: 'pozitie' },
  { key: 'destinatie', label: 'Destinație', sortKey: 'destinatie' },
  { key: 'etapa_parc', label: 'Etapă Parc', sortKey: 'etapa_parc' },
  { key: 'predare', label: 'Predare', sortKey: 'predare' },
  { key: 'vin', label: 'VIN', sortKey: 'vin' },
]

export default function Parc() {
  const navigate = useNavigate()
  const location = useLocation()
  const [, setSearchParams] = useSearchParams()

  // The URL querystring is the single source of truth for filters+sort, so
  // Back/forward and a reload both restore exactly what was showing --
  // the "Back restores filters + sort" requirement (§4.1).
  const filters = useMemo(() => parseParcFiltersFromSearch(location.search), [location.search])
  const apiFilters = useMemo(() => toListVehiclesFilters(filters), [filters])

  const { data, isFetching, error } = useQuery({
    queryKey: ['logistics', 'vehicles', apiFilters],
    queryFn: () => logisticsApi.listVehicles(apiFilters),
  })

  // Separate, unfiltered (company-wide) fetch purely to populate the
  // Locație dropdown -- so narrowing by etapă/destinație/predare doesn't
  // also shrink which locations are offered as a filter.
  const { data: allData } = useQuery({
    queryKey: ['logistics', 'vehicles', 'all-for-location-options'],
    queryFn: () => logisticsApi.listVehicles({}),
  })
  const locationOptions = useMemo(
    () => distinctLocationOptions(allData?.vehicles ?? []),
    [allData],
  )

  const rows = data?.vehicles ?? []

  function updateFilters(patch: Partial<ParcFiltersState>) {
    const next: ParcFiltersState = { ...filters, ...patch }
    setSearchParams(buildParcSearchParams(next), { replace: true })
  }

  function handleSort(column: string) {
    updateFilters(nextSort(filters, column))
  }

  function handleReset() {
    setSearchParams(buildParcSearchParams(EMPTY_PARC_FILTERS), { replace: true })
  }

  function handleRowClick(row: ParcVehicleRow) {
    const qs = buildParcSearchParams(filters).toString()
    navigate(`/app/logistics/parc/${row.id}${qs ? `?${qs}` : ''}`)
  }

  return (
    <div className="space-y-4">
      <PageHeader title="Parc" description="Registrul auto — toate mașinile în custodie" />

      <div className="flex flex-wrap items-end gap-2">
        <SearchInput
          value={filters.q}
          onChange={(q) => updateFilters({ q })}
          placeholder="VIN, comandă, model sau număr..."
          className="w-full sm:w-64"
        />

        <Select
          value={filters.location_id || 'all'}
          onValueChange={(v) => updateFilters({ location_id: v === 'all' ? '' : v })}
        >
          <SelectTrigger className="w-full sm:w-44" aria-label="Locație">
            <SelectValue placeholder="Locație" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Toate locațiile</SelectItem>
            {locationOptions.map((loc) => (
              <SelectItem key={loc.id} value={String(loc.id)}>{loc.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>

        <Select
          value={filters.destinatie || 'all'}
          onValueChange={(v) => updateFilters({ destinatie: v === 'all' ? '' : v })}
        >
          <SelectTrigger className="w-full sm:w-40" aria-label="Destinație">
            <SelectValue placeholder="Destinație" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Toate destinațiile</SelectItem>
            {DESTINATIE_OPTIONS.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}
          </SelectContent>
        </Select>

        <Select
          value={filters.etapa || 'all'}
          onValueChange={(v) => updateFilters({ etapa: v === 'all' ? '' : v })}
        >
          <SelectTrigger className="w-full sm:w-40" aria-label="Etapă Parc">
            <SelectValue placeholder="Etapă" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Toate etapele</SelectItem>
            {ETAPA_OPTIONS.map((e) => <SelectItem key={e} value={e}>{e}</SelectItem>)}
          </SelectContent>
        </Select>

        <Select
          value={filters.predare || 'all'}
          onValueChange={(v) => updateFilters({ predare: v === 'all' ? '' : v })}
        >
          <SelectTrigger className="w-full sm:w-44" aria-label="Predare">
            <SelectValue placeholder="Predare" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem value="all">Toate stările</SelectItem>
            {PREDARE_OPTIONS.map((p) => <SelectItem key={p} value={p}>{p}</SelectItem>)}
          </SelectContent>
        </Select>

        <Button variant="outline" onClick={handleReset}>Resetează</Button>
      </div>

      {error ? (
        <EmptyState
          title="Eroare la încărcare"
          description={extractErrorMessage(error)}
        />
      ) : !isFetching && rows.length === 0 ? (
        <EmptyState
          title="Niciun rezultat"
          description="Nicio mașină nu corespunde filtrelor curente."
        />
      ) : (
        // The shared Table component already wraps itself in a
        // `overflow-x-auto` container -- on mobile the table scrolls
        // horizontally while the first (Vehicul) column stays pinned via
        // `sticky left-0` below (§4.1 "Mobile: Vehicul column stays
        // pinned/visible; the rest scroll horizontally").
        <div className="rounded-md border">
          <Table>
            <TableHeader>
              <TableRow>
                {COLUMNS.map((col, idx) => (
                  <TableHead
                    key={col.key}
                    onClick={() => handleSort(col.sortKey)}
                    className={cn(
                      'cursor-pointer select-none',
                      idx === 0 && 'sticky left-0 z-10 bg-muted',
                    )}
                  >
                    <span className="inline-flex items-center gap-1">
                      {col.label}
                      {filters.sort === col.sortKey ? (
                        filters.dir === 'desc'
                          ? <ArrowDown className="h-3 w-3" />
                          : <ArrowUp className="h-3 w-3" />
                      ) : (
                        <ArrowUpDown className="h-3 w-3 text-muted-foreground/40" />
                      )}
                    </span>
                  </TableHead>
                ))}
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map((row) => (
                <TableRow
                  key={row.id}
                  onClick={() => handleRowClick(row)}
                  className="cursor-pointer"
                >
                  <TableCell className="sticky left-0 z-10 bg-background font-medium">
                    {row.vehicul || '—'}
                  </TableCell>
                  <TableCell>{row.comanda}</TableCell>
                  <TableCell>{row.locatie || '—'}</TableCell>
                  <TableCell>{row.pozitie || '—'}</TableCell>
                  <TableCell>{row.destinatie || '—'}</TableCell>
                  <TableCell>
                    <Badge variant="secondary">{row.etapa_parc}</Badge>
                  </TableCell>
                  <TableCell>
                    <Badge variant={row.predare === 'Blocat' ? 'destructive' : 'outline'}>
                      {row.predare}
                    </Badge>
                  </TableCell>
                  <TableCell className="font-mono text-xs">{row.vin || '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      )}
    </div>
  )
}
