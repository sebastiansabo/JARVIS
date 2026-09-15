import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { carparkApi } from '@/api/carpark'

const CADENCE_OPTIONS: { value: string; label: string }[] = [
  { value: 'manual', label: 'Manual' },
  { value: 'instant', label: 'Instant' },
  { value: '2h', label: 'La 2 ore' },
  { value: '3h', label: 'La 3 ore' },
  { value: '5h', label: 'La 5 ore' },
  { value: 'daily', label: 'Zilnic' },
]

const rel = (iso?: string | null) => {
  if (!iso) return null
  const d = new Date(iso)
  return new Intl.DateTimeFormat('ro-RO', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  }).format(d)
}

// ── Per-vehicle auto-update cadence selector (Shopify Anunțuri panel) ──
export function ListingScheduleSelect({
  vehicleId,
  platform,
}: {
  vehicleId: number
  platform: string
}) {
  const queryClient = useQueryClient()
  const queryKey = ['listing-schedule', vehicleId, platform]

  const { data, isLoading } = useQuery({
    queryKey,
    queryFn: () => carparkApi.getListingSchedule(vehicleId, platform),
    enabled: !!vehicleId,
  })

  const schedule = data?.schedule ?? null
  const cadence = schedule?.cadence ?? 'manual'

  const mutation = useMutation({
    mutationFn: (newCadence: string) =>
      carparkApi.setListingSchedule(vehicleId, {
        platform,
        cadence: newCadence,
        enabled: true,
      }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey })
    },
    onError: () => {
      toast.error('Salvarea programării a eșuat')
    },
  })

  return (
    <div className="flex flex-col items-end gap-1">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">Actualizare automată</span>
        <Select
          value={cadence}
          onValueChange={(v) => mutation.mutate(v)}
          disabled={isLoading || mutation.isPending}
        >
          <SelectTrigger size="sm" className="w-44">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {CADENCE_OPTIONS.map((opt) => (
              <SelectItem key={opt.value} value={opt.value}>
                {opt.label}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
      {schedule?.next_run_at && (
        <span className="text-[11px] text-muted-foreground">
          Următoarea sincronizare: {rel(schedule.next_run_at)}
        </span>
      )}
    </div>
  )
}

export default ListingScheduleSelect
