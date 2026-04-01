import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { Button } from '@/components/ui/button'
import { Badge } from '@/components/ui/badge'
import { Checkbox } from '@/components/ui/checkbox'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  AlertTriangle, Building2, CheckCircle2, GitMerge, Loader2,
  RefreshCw, Shield, Sparkles, ArrowRight,
} from 'lucide-react'
import { crmApi } from '@/api/crm'
import { toast } from 'sonner'

export default function SanitizeTab() {
  const queryClient = useQueryClient()
  const [selectedTypes, setSelectedTypes] = useState<Set<number>>(new Set())
  const [mergedPairs, setMergedPairs] = useState<Set<string>>(new Set())

  const { data, isLoading, refetch } = useQuery({
    queryKey: ['crm-sanitize'],
    queryFn: () => crmApi.sanitizeScan(),
  })

  const fixTypesMutation = useMutation({
    mutationFn: (ids: number[]) => crmApi.sanitizeFixTypes(ids),
    onSuccess: (res) => {
      queryClient.invalidateQueries({ queryKey: ['crm-sanitize'] })
      queryClient.invalidateQueries({ queryKey: ['crm-clients'] })
      queryClient.invalidateQueries({ queryKey: ['crm-stats'] })
      toast.success(`${res.affected} clienti actualizati la tipul "company"`)
      setSelectedTypes(new Set())
    },
    onError: () => toast.error('Eroare la actualizare'),
  })

  const mergeMutation = useMutation({
    mutationFn: ({ keepId, removeId }: { keepId: number; removeId: number }) =>
      crmApi.mergeClients(keepId, removeId),
    onSuccess: (_, vars) => {
      queryClient.invalidateQueries({ queryKey: ['crm-sanitize'] })
      queryClient.invalidateQueries({ queryKey: ['crm-clients'] })
      queryClient.invalidateQueries({ queryKey: ['crm-stats'] })
      setMergedPairs(prev => new Set([...prev, `${vars.keepId}-${vars.removeId}`]))
      toast.success('Clienti unificati cu succes')
    },
    onError: () => toast.error('Eroare la unificare'),
  })

  const wrongTypes = data?.wrong_types ?? []
  const mergeSuggestions = data?.merge_suggestions ?? []

  const toggleType = (id: number) => {
    setSelectedTypes(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const selectAllTypes = () => {
    if (selectedTypes.size === wrongTypes.length) setSelectedTypes(new Set())
    else setSelectedTypes(new Set(wrongTypes.map(c => c.id)))
  }

  return (
    <div className="space-y-4">
      {/* Header */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-base flex items-center gap-2">
              <Sparkles className="h-4 w-4 text-primary" />
              Asistent Sanitizare Date
            </CardTitle>
            <Button variant="outline" size="sm" onClick={() => refetch()} disabled={isLoading}>
              <RefreshCw className={`h-3.5 w-3.5 mr-1 ${isLoading ? 'animate-spin' : ''}`} />
              Re-scanare
            </Button>
          </div>
          <p className="text-sm text-muted-foreground mt-1">
            Detectare automata a problemelor de calitate a datelor: tipuri incorecte si clienti duplicat.
          </p>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-2 gap-4">
            <div className="rounded-lg border p-4 text-center">
              <div className="text-2xl font-bold text-amber-600">{data?.wrong_types_count ?? '...'}</div>
              <div className="text-xs text-muted-foreground mt-1">Tip incorect (companii marcate ca persoana)</div>
            </div>
            <div className="rounded-lg border p-4 text-center">
              <div className="text-2xl font-bold text-blue-600">{data?.merge_suggestions_count ?? '...'}</div>
              <div className="text-xs text-muted-foreground mt-1">Sugestii de unificare (duplicat)</div>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Wrong Types */}
      <Card>
        <CardHeader className="pb-3">
          <div className="flex items-center justify-between">
            <CardTitle className="text-sm flex items-center gap-1.5">
              <AlertTriangle className="h-4 w-4 text-amber-500" />
              Tip Incorect — Companii Marcate ca "person" ({wrongTypes.length})
            </CardTitle>
            {selectedTypes.size > 0 && (
              <Button
                size="sm"
                onClick={() => fixTypesMutation.mutate([...selectedTypes])}
                disabled={fixTypesMutation.isPending}
              >
                {fixTypesMutation.isPending ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin mr-1" />
                ) : (
                  <CheckCircle2 className="h-3.5 w-3.5 mr-1" />
                )}
                Corecteaza {selectedTypes.size} selectat{selectedTypes.size > 1 ? 'i' : ''}
              </Button>
            )}
          </div>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center gap-2 py-4 justify-center text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />Se scaneaza...
            </div>
          ) : wrongTypes.length === 0 ? (
            <div className="flex items-center gap-2 py-4 justify-center text-green-600">
              <CheckCircle2 className="h-4 w-4" />Toate tipurile sunt corecte!
            </div>
          ) : (
            <>
              {wrongTypes.length > 3 && (
                <div className="flex items-center gap-2 mb-2">
                  <Button variant="outline" size="sm" className="h-7 text-xs" onClick={selectAllTypes}>
                    {selectedTypes.size === wrongTypes.length ? 'Deselecteaza tot' : 'Selecteaza tot'}
                  </Button>
                  <Button
                    size="sm" className="h-7 text-xs"
                    onClick={() => fixTypesMutation.mutate(wrongTypes.map(c => c.id))}
                    disabled={fixTypesMutation.isPending}
                  >
                    <Shield className="h-3 w-3 mr-1" />
                    Corecteaza toate ({wrongTypes.length})
                  </Button>
                </div>
              )}
              <div className="rounded border overflow-hidden">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/50">
                      <TableHead className="w-8 px-2">
                        <Checkbox
                          checked={wrongTypes.length > 0 && selectedTypes.size === wrongTypes.length}
                          onCheckedChange={selectAllTypes}
                        />
                      </TableHead>
                      <TableHead className="text-xs py-1.5">Nume</TableHead>
                      <TableHead className="text-xs py-1.5">Tip Actual</TableHead>
                      <TableHead className="text-xs py-1.5">Nr. Reg</TableHead>
                      <TableHead className="text-xs py-1.5">Telefon</TableHead>
                      <TableHead className="text-xs py-1.5">Oras</TableHead>
                      <TableHead className="text-xs py-1.5 text-right">Actiune</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {wrongTypes.map(c => (
                      <TableRow key={c.id}>
                        <TableCell className="px-2">
                          <Checkbox
                            checked={selectedTypes.has(c.id)}
                            onCheckedChange={() => toggleType(c.id)}
                          />
                        </TableCell>
                        <TableCell className="text-xs py-1.5 font-medium">{c.display_name}</TableCell>
                        <TableCell className="py-1.5">
                          <Badge variant="secondary" className="text-[10px]">{c.client_type}</Badge>
                          <ArrowRight className="inline h-3 w-3 mx-1 text-muted-foreground" />
                          <Badge variant="default" className="text-[10px]">company</Badge>
                        </TableCell>
                        <TableCell className="text-xs py-1.5 font-mono">{c.nr_reg || '—'}</TableCell>
                        <TableCell className="text-xs py-1.5 font-mono">{c.phone || '—'}</TableCell>
                        <TableCell className="text-xs py-1.5">{c.city || '—'}</TableCell>
                        <TableCell className="text-xs py-1.5 text-right">
                          <Button
                            variant="ghost" size="sm" className="h-6 text-xs"
                            onClick={() => fixTypesMutation.mutate([c.id])}
                            disabled={fixTypesMutation.isPending}
                          >
                            Corecteaza
                          </Button>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Merge Suggestions */}
      <Card>
        <CardHeader className="pb-3">
          <CardTitle className="text-sm flex items-center gap-1.5">
            <GitMerge className="h-4 w-4 text-blue-500" />
            Sugestii de Unificare — Clienti Duplicat ({mergeSuggestions.length})
          </CardTitle>
        </CardHeader>
        <CardContent>
          {isLoading ? (
            <div className="flex items-center gap-2 py-4 justify-center text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" />Se scaneaza...
            </div>
          ) : mergeSuggestions.length === 0 ? (
            <div className="flex items-center gap-2 py-4 justify-center text-green-600">
              <CheckCircle2 className="h-4 w-4" />Nu s-au detectat duplicate!
            </div>
          ) : (
            <div className="space-y-3">
              {mergeSuggestions.map((group, idx) => {
                const pairKey = `${group.suggested_keep_id}-${group.suggested_remove_id}`
                const isMerged = mergedPairs.has(pairKey)
                const keepClient = group.suggested_keep_id === group.client_a.id ? group.client_a : group.client_b
                const removeClient = group.suggested_remove_id === group.client_a.id ? group.client_a : group.client_b

                return (
                  <div
                    key={idx}
                    className={`rounded-lg border p-3 ${isMerged ? 'opacity-50 bg-green-50 dark:bg-green-950/20' : ''}`}
                  >
                    <div className="flex items-center justify-between mb-2">
                      <div className="flex items-center gap-2">
                        <Badge variant="outline" className="text-[10px]">
                          {Math.round(group.similarity * 100)}% similar
                        </Badge>
                        {isMerged && (
                          <Badge variant="default" className="text-[10px] bg-green-600">
                            <CheckCircle2 className="h-2.5 w-2.5 mr-0.5" />Unificat
                          </Badge>
                        )}
                      </div>
                      {!isMerged && (
                        <Button
                          size="sm" className="h-7 text-xs"
                          onClick={() => mergeMutation.mutate({
                            keepId: group.suggested_keep_id,
                            removeId: group.suggested_remove_id,
                          })}
                          disabled={mergeMutation.isPending}
                        >
                          {mergeMutation.isPending ? (
                            <Loader2 className="h-3 w-3 animate-spin mr-1" />
                          ) : (
                            <GitMerge className="h-3 w-3 mr-1" />
                          )}
                          Unifica
                        </Button>
                      )}
                    </div>

                    <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                      {/* Keep */}
                      <div className="rounded border border-green-200 dark:border-green-900 p-2.5 bg-green-50/50 dark:bg-green-950/20">
                        <p className="text-[10px] text-green-600 font-medium uppercase mb-1 flex items-center gap-1">
                          <CheckCircle2 className="h-2.5 w-2.5" /> Pastreaza (ID: {keepClient.id})
                        </p>
                        <p className="text-sm font-medium">{keepClient.display_name}</p>
                        <div className="grid grid-cols-2 gap-x-3 mt-1 text-xs text-muted-foreground">
                          <span>Tip: <Badge variant={keepClient.client_type === 'company' ? 'default' : 'secondary'} className="text-[9px] px-1 py-0">{keepClient.client_type}</Badge></span>
                          <span>Nr.Reg: {keepClient.nr_reg || '—'}</span>
                          <span>Tel: {keepClient.phone || '—'}</span>
                          <span>Email: {keepClient.email || '—'}</span>
                          <span>Oras: {keepClient.city || '—'}</span>
                        </div>
                      </div>

                      {/* Remove */}
                      <div className="rounded border border-red-200 dark:border-red-900 p-2.5 bg-red-50/50 dark:bg-red-950/20">
                        <p className="text-[10px] text-red-600 font-medium uppercase mb-1 flex items-center gap-1">
                          <Building2 className="h-2.5 w-2.5" /> Unifica in (ID: {removeClient.id})
                        </p>
                        <p className="text-sm font-medium">{removeClient.display_name}</p>
                        <div className="grid grid-cols-2 gap-x-3 mt-1 text-xs text-muted-foreground">
                          <span>Tip: <Badge variant={removeClient.client_type === 'company' ? 'default' : 'secondary'} className="text-[9px] px-1 py-0">{removeClient.client_type}</Badge></span>
                          <span>Nr.Reg: {removeClient.nr_reg || '—'}</span>
                          <span>Tel: {removeClient.phone || '—'}</span>
                          <span>Email: {removeClient.email || '—'}</span>
                          <span>Oras: {removeClient.city || '—'}</span>
                        </div>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  )
}
