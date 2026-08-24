import { useState } from 'react'
import { ChevronRight, Pencil, Plus } from 'lucide-react'
import { Card, CardContent } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { useAdminPulses, usePulseResults, type AdminPulse } from '@/api/happyAdmin'
import { PulseEditor, NewPulseDialog } from './PulseEditor'
import { PulseResultsView } from './PulseResultsView'
import { StatusBadge } from './StatusBadge'

/** One pulse row that expands in place to show its live report. */
function PulseRow({
  pulse,
  expanded,
  onToggle,
  onEdit,
}: {
  pulse: AdminPulse
  expanded: boolean
  onToggle: () => void
  onEdit: () => void
}) {
  // Fetch the report only while expanded; poll while the pulse is live.
  const { data: results, isLoading } = usePulseResults(expanded ? pulse.id : null, pulse.status === 'live')

  return (
    <>
      <TableRow className="cursor-pointer" onClick={onToggle}>
        <TableCell className="w-8 pr-0 text-muted-foreground">
          <ChevronRight className={`h-4 w-4 transition-transform ${expanded ? 'rotate-90' : ''}`} />
        </TableCell>
        <TableCell className="font-medium">{pulse.title}</TableCell>
        <TableCell className="text-muted-foreground">{pulse.cadence}</TableCell>
        <TableCell>
          <StatusBadge status={pulse.status} />
        </TableCell>
        <TableCell className="text-right">
          <Button
            size="sm"
            variant="ghost"
            onClick={(e) => {
              e.stopPropagation()
              onEdit()
            }}
          >
            <Pencil className="h-3.5 w-3.5" /> Editează
          </Button>
        </TableCell>
      </TableRow>
      {expanded && (
        <TableRow className="hover:bg-transparent">
          <TableCell colSpan={5} className="bg-muted/30">
            {isLoading ? (
              <Skeleton className="h-32 w-full" />
            ) : results ? (
              <PulseResultsView results={results} />
            ) : (
              <p className="text-sm text-muted-foreground">Nu am putut încărca raportul.</p>
            )}
          </TableCell>
        </TableRow>
      )}
    </>
  )
}

export function PulseTab() {
  const { data, isLoading } = useAdminPulses()
  const [expanded, setExpanded] = useState<number | null>(null)
  const [editing, setEditing] = useState<number | null>(null)
  const [creating, setCreating] = useState(false)
  const pulses = data?.pulses ?? []

  return (
    <div className="space-y-4">
      <div className="flex justify-end">
        <Button size="sm" onClick={() => setCreating(true)}>
          <Plus className="h-3.5 w-3.5" /> Pulse nou
        </Button>
      </div>

      {isLoading ? (
        <Skeleton className="h-40 w-full" />
      ) : pulses.length === 0 ? (
        <Card>
          <CardContent className="py-10 text-center text-sm text-muted-foreground">
            Niciun pulse creat.
          </CardContent>
        </Card>
      ) : (
        <Card>
          <CardContent className="pt-6">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-8" />
                  <TableHead>Titlu</TableHead>
                  <TableHead>Cadență</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Acțiuni</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {pulses.map((p) => (
                  <PulseRow
                    key={p.id}
                    pulse={p}
                    expanded={expanded === p.id}
                    onToggle={() => setExpanded((cur) => (cur === p.id ? null : p.id))}
                    onEdit={() => setEditing(p.id)}
                  />
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      <PulseEditor pulseId={editing} open={editing != null} onOpenChange={(o) => !o && setEditing(null)} />
      <NewPulseDialog open={creating} onOpenChange={setCreating} />
    </div>
  )
}

export default PulseTab
