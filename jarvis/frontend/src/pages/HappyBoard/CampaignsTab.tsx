import { useState } from 'react'
import { Plus } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { useAdminCampaigns, type HappyTier } from '@/api/happyAdmin'
import { CampaignEditor } from './CampaignEditor'

const TIER_VARIANT: Record<HappyTier, 'destructive' | 'secondary' | 'outline'> = {
  critical: 'destructive',
  important: 'secondary',
  normal: 'outline',
}

const STATUS_FILTERS = ['all', 'draft', 'live', 'paused', 'archived']

export function CampaignsTab() {
  const [status, setStatus] = useState('all')
  const { data, isLoading } = useAdminCampaigns(status === 'all' ? undefined : status)
  const [editorId, setEditorId] = useState<number | null>(null)
  const [editorOpen, setEditorOpen] = useState(false)

  const campaigns = data?.campaigns ?? []

  const openNew = () => {
    setEditorId(null)
    setEditorOpen(true)
  }
  const openEdit = (id: number) => {
    setEditorId(id)
    setEditorOpen(true)
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <Select value={status} onValueChange={setStatus}>
          <SelectTrigger className="w-40">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {STATUS_FILTERS.map((s) => (
              <SelectItem key={s} value={s}>
                {s === 'all' ? 'Toate' : s}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Button size="sm" onClick={openNew}>
          <Plus className="h-3.5 w-3.5" /> Campanie nouă
        </Button>
      </div>

      {isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : campaigns.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Nicio campanie.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="pt-6">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Titlu</TableHead>
                  <TableHead>Tip</TableHead>
                  <TableHead>Nivel</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Plasări</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {campaigns.map((c) => (
                  <TableRow
                    key={c.id}
                    className="cursor-pointer"
                    onClick={() => openEdit(c.id)}
                  >
                    <TableCell className="font-medium">{c.title}</TableCell>
                    <TableCell className="text-muted-foreground">{c.kind}</TableCell>
                    <TableCell>
                      <Badge variant={TIER_VARIANT[c.tier] ?? 'outline'}>{c.tier}</Badge>
                    </TableCell>
                    <TableCell>
                      <Badge variant="outline">{c.status}</Badge>
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {(c.placements ?? []).join(', ')}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <CampaignEditor campaignId={editorId} open={editorOpen} onOpenChange={setEditorOpen} />
    </div>
  )
}

export default CampaignsTab
