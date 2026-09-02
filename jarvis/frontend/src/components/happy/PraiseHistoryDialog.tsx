import { useState } from 'react'
import { useQuery, keepPreviousData } from '@tanstack/react-query'
import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog'
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Skeleton } from '@/components/ui/skeleton'
import { praiseApi } from '@/api/happy'
import type {
  HappyKudosVisibility,
  HappyReceivedKudos,
  HappyReceivedResponse,
  HappySentKudos,
  HappySentResponse,
} from '@/types/happy'
import { personLabel, timeAgo } from './praiseFormat'

const PAGE = 15

const VISIBILITY_LABEL: Record<HappyKudosVisibility, string> = {
  company: 'Companie',
  department: 'Departament',
  private: 'Privat',
}

interface KudosListProps {
  mode: 'received' | 'sent'
}

/** A paginated list of the caller's received or sent kudos, with load-more. */
function KudosList({ mode }: KudosListProps) {
  const [limit, setLimit] = useState(PAGE)

  const { data, isLoading, isFetching } = useQuery<HappyReceivedResponse | HappySentResponse>({
    queryKey: ['happy', 'praise', mode, limit],
    queryFn: () =>
      mode === 'received' ? praiseApi.getReceived(limit) : praiseApi.getSent(limit),
    placeholderData: keepPreviousData,
    staleTime: 30_000,
  })

  if (isLoading) {
    return (
      <div className="space-y-2">
        {[1, 2, 3, 4].map((i) => (
          <Skeleton key={i} className="h-16 w-full" />
        ))}
      </div>
    )
  }

  const items = data?.items ?? []
  if (items.length === 0) {
    return (
      <p className="py-10 text-center text-sm text-muted-foreground">
        {mode === 'received' ? 'Încă nu ai primit aprecieri.' : 'Încă nu ai trimis aprecieri.'}
      </p>
    )
  }

  // If the server returned exactly `limit` rows, there is probably another page.
  const maybeMore = items.length >= limit

  return (
    <div className="space-y-2">
      {items.map((k) => {
        const recv = k as HappyReceivedKudos
        const sent = k as HappySentKudos
        const person =
          mode === 'received'
            ? personLabel(recv.from_name, recv.from_user)
            : personLabel(sent.to_name, sent.to_user)
        const visibility: HappyKudosVisibility | null = mode === 'sent' ? sent.visibility : null
        return (
          <div key={k.id} className="rounded-lg border p-3">
            <div className="mb-1 flex items-center justify-between gap-2">
              <div className="flex items-center gap-1.5">
                {k.value_label ? <Badge variant="secondary">{k.value_label}</Badge> : <span />}
                {visibility && (
                  <Badge variant="outline" className="text-[10px] font-normal">
                    {VISIBILITY_LABEL[visibility]}
                  </Badge>
                )}
              </div>
              <span className="whitespace-nowrap text-xs text-muted-foreground">
                {timeAgo(k.created_at)}
              </span>
            </div>
            <p className="text-sm">{k.note}</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {mode === 'received' ? 'de la ' : 'către '}
              {person}
            </p>
          </div>
        )
      })}

      {maybeMore && (
        <div className="pt-1 text-center">
          <Button
            variant="ghost"
            size="sm"
            disabled={isFetching}
            onClick={() => setLimit((l) => l + PAGE)}
          >
            {isFetching ? 'Se încarcă…' : 'Încarcă mai multe'}
          </Button>
        </div>
      )}
    </div>
  )
}

interface PraiseHistoryDialogProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

/** Full history of the caller's appreciations — received and sent — in a dialog. */
export function PraiseHistoryDialog({ open, onOpenChange }: PraiseHistoryDialogProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle>Aprecierile mele</DialogTitle>
        </DialogHeader>
        <Tabs defaultValue="received">
          <TabsList className="grid w-full grid-cols-2">
            <TabsTrigger value="received">Primite</TabsTrigger>
            <TabsTrigger value="sent">Trimise</TabsTrigger>
          </TabsList>
          <TabsContent value="received" className="mt-3 max-h-[60vh] overflow-y-auto pr-1">
            <KudosList mode="received" />
          </TabsContent>
          <TabsContent value="sent" className="mt-3 max-h-[60vh] overflow-y-auto pr-1">
            <KudosList mode="sent" />
          </TabsContent>
        </Tabs>
      </DialogContent>
    </Dialog>
  )
}

export default PraiseHistoryDialog
