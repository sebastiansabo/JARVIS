import { Card, CardContent } from '@/components/ui/card'
import { Badge } from '@/components/ui/badge'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import { Skeleton } from '@/components/ui/skeleton'
import { usePraiseFlags } from '@/api/happyAdmin'

const RULE_LABELS: Record<string, string> = {
  reciprocity: 'Reciprocitate',
  burst: 'Rafală',
  duplicate_text: 'Text duplicat',
  deadline_dump: 'Aglomerare la termen',
  cap_exceeded: 'Limită depășită',
}

/** Flagged-kudos moderation queue. No leaderboards, no rankings. */
export function PraiseTab() {
  const { data, isLoading } = usePraiseFlags()
  const flags = data?.flags ?? []

  if (isLoading) return <Skeleton className="h-40 w-full" />

  if (flags.length === 0) {
    return (
      <Card>
        <CardContent className="py-10 text-center text-sm text-muted-foreground">
          Nicio apreciere semnalată.
        </CardContent>
      </Card>
    )
  }

  return (
    <Card>
      <CardContent className="pt-6">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Regulă</TableHead>
              <TableHead>Kudos</TableHead>
              <TableHead>Perioadă</TableHead>
              <TableHead>Semnalat</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {flags.map((f) => (
              <TableRow key={f.id}>
                <TableCell>
                  <Badge variant="destructive">{RULE_LABELS[f.rule] ?? f.rule}</Badge>
                </TableCell>
                <TableCell className="text-muted-foreground">#{f.kudos_id}</TableCell>
                <TableCell className="text-muted-foreground">{f.period}</TableCell>
                <TableCell className="text-muted-foreground">
                  {new Date(f.created_at).toLocaleDateString('ro-RO')}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  )
}

export default PraiseTab
