import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Globe, Loader2, Undo2 } from 'lucide-react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { shopifyApi } from '@/api/shopify'
import { ListingFreshness } from './ListingFreshness'

// ── Shopify publish control (status chip + publish/retract button) ──
export function ShopifyPublishControl({
  vehicleId,
  canEdit,
}: {
  vehicleId: number
  canEdit: boolean
}) {
  const queryClient = useQueryClient()
  const statusKey = ['shopify', 'status', vehicleId]

  const { data, isLoading } = useQuery({
    queryKey: statusKey,
    queryFn: () => shopifyApi.vehicleStatus(vehicleId),
    enabled: !!vehicleId,
  })

  const listing = data?.listing ?? null
  const isPublished = listing?.status === 'published'

  const invalidateStatus = () => queryClient.invalidateQueries({ queryKey: statusKey })

  const publishMutation = useMutation({
    mutationFn: () => shopifyApi.publishVehicle(vehicleId),
    onSuccess: (res) => {
      invalidateStatus()
      toast.success('Publicat pe Shopify')
      if (res.warnings && res.warnings.length > 0) {
        toast.info(
          `Nemapate: ${res.warnings.join(', ')} — vezi Setări → Shopify → Taxonomie`,
        )
      }
    },
    onError: (err: unknown) => {
      const msg = (err as { data?: { error?: string } })?.data?.error || 'Publicare eșuată'
      toast.error(msg)
    },
  })

  const unpublishMutation = useMutation({
    mutationFn: () => shopifyApi.unpublishVehicle(vehicleId),
    onSuccess: () => {
      invalidateStatus()
      toast.success('Retras de pe Shopify')
    },
    onError: (err: unknown) => {
      const msg = (err as { data?: { error?: string } })?.data?.error || 'Retragere eșuată'
      toast.error(msg)
    },
  })

  const isMutating = publishMutation.isPending || unpublishMutation.isPending

  return (
    <div className="flex items-center gap-2">
      {!isLoading && (
        <ListingFreshness
          freshness={data?.freshness ?? 'not_published'}
          lastSync={listing?.last_sync}
          expiresAt={listing?.expires_at}
        />
      )}
      {canEdit && (
        <Button
          size="sm"
          variant={isPublished ? 'outline' : 'default'}
          className="w-44"
          disabled={isMutating || isLoading}
          onClick={() => (isPublished ? unpublishMutation.mutate() : publishMutation.mutate())}
        >
          {isMutating ? (
            <Loader2 className="mr-1.5 h-3.5 w-3.5 animate-spin" />
          ) : isPublished ? (
            <Undo2 className="mr-1.5 h-3.5 w-3.5" />
          ) : (
            <Globe className="mr-1.5 h-3.5 w-3.5" />
          )}
          {isPublished ? 'Retrage' : 'Publică pe Shopify'}
        </Button>
      )}
    </div>
  )
}

export default ShopifyPublishControl
