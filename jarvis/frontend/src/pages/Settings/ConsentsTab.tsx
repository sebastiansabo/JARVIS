import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { AlertTriangle, Plus } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'
import { Textarea } from '@/components/ui/textarea'
import { Badge } from '@/components/ui/badge'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { EmptyState } from '@/components/shared/EmptyState'
import { toast } from 'sonner'
import { consentsApi } from '@/api/consents'
import type {
  ConsentDocumentAdmin,
  CreateConsentDocumentPayload,
  UpdateConsentDocumentPayload,
} from '@/api/consents'

interface DocDraft {
  title: string
  body: string
  sort_order: number
  is_active: boolean
}

function draftFromDoc(doc: ConsentDocumentAdmin): DocDraft {
  return { title: doc.title, body: doc.body, sort_order: doc.sort_order, is_active: doc.is_active }
}

export default function ConsentsTab() {
  const queryClient = useQueryClient()
  const [drafts, setDrafts] = useState<Record<number, DocDraft>>({})
  const [showAdd, setShowAdd] = useState(false)

  const { data, isLoading } = useQuery({
    queryKey: ['settings', 'consent-documents'],
    queryFn: () => consentsApi.listDocuments(),
    staleTime: 60_000,
  })

  const docs = data?.documents ?? []

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: UpdateConsentDocumentPayload }) =>
      consentsApi.updateDocument(id, payload),
    onSuccess: (_result, variables) => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'consent-documents'] })
      setDrafts((prev) => {
        const next = { ...prev }
        delete next[variables.id]
        return next
      })
      toast.success('Document salvat')
    },
    onError: () => toast.error('Salvarea documentului a eșuat'),
  })

  const createMutation = useMutation({
    mutationFn: (payload: CreateConsentDocumentPayload) => consentsApi.createDocument(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['settings', 'consent-documents'] })
      setShowAdd(false)
      toast.success('Document creat')
    },
    onError: () => toast.error('Crearea documentului a eșuat'),
  })

  const getDraft = (doc: ConsentDocumentAdmin): DocDraft => drafts[doc.id] ?? draftFromDoc(doc)

  const setDraft = (doc: ConsentDocumentAdmin, patch: Partial<DocDraft>) => {
    setDrafts((prev) => ({ ...prev, [doc.id]: { ...(prev[doc.id] ?? draftFromDoc(doc)), ...patch } }))
  }

  const isDirty = (doc: ConsentDocumentAdmin) => {
    const d = drafts[doc.id]
    if (!d) return false
    return (
      d.title !== doc.title ||
      d.body !== doc.body ||
      d.sort_order !== doc.sort_order ||
      d.is_active !== doc.is_active
    )
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between gap-3">
            <div>
              <CardTitle>Acorduri (documente legale)</CardTitle>
              <CardDescription>
                Editați textul acordurilor (GDPR, prelucrare date, NDA) afișate utilizatorilor.
              </CardDescription>
            </div>
            <Button size="sm" onClick={() => setShowAdd(true)}>
              <Plus className="mr-1.5 h-4 w-4" />
              Document nou
            </Button>
          </div>
        </CardHeader>
        <CardContent>
          <div className="flex gap-2 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-800 dark:border-amber-900 dark:bg-amber-950/30 dark:text-amber-300">
            <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
            <div className="space-y-1">
              <p className="font-medium">
                Editarea textului NU obligă utilizatorii care au semnat deja să semneze din nou (v1).
              </p>
              <p>
                La modificarea textului (body), numărul de versiune al documentului se incrementează automat,
                dar semnăturile existente rămân valabile — utilizatorii nu sunt re-solicitați. Activați un
                document ("Activ") doar după validarea juridică a textului.
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {isLoading ? (
        <div className="space-y-3">
          {Array.from({ length: 3 }).map((_, i) => (
            <div key={i} className="h-40 animate-pulse rounded-lg border bg-muted" />
          ))}
        </div>
      ) : docs.length === 0 ? (
        <EmptyState title="Niciun document" description="Nu există documente de acorduri configurate." />
      ) : (
        <div className="space-y-4">
          {docs.map((doc) => {
            const draft = getDraft(doc)
            const dirty = isDirty(doc)
            const pending = updateMutation.isPending && updateMutation.variables?.id === doc.id
            return (
              <Card key={doc.id}>
                <CardHeader>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div className="flex flex-wrap items-center gap-2">
                      <Badge variant="secondary" className="font-mono">{doc.doc_key}</Badge>
                      <Badge variant="outline">v{doc.version}</Badge>
                      {doc.is_mandatory && <Badge variant="outline">Obligatoriu</Badge>}
                      {doc.requires_signature && <Badge variant="outline">Necesită semnătură</Badge>}
                    </div>
                    <div className="flex items-center gap-2">
                      <Label className="text-xs text-muted-foreground">Activ</Label>
                      <Switch
                        checked={draft.is_active}
                        onCheckedChange={(checked) => setDraft(doc, { is_active: checked })}
                      />
                    </div>
                  </div>
                </CardHeader>
                <CardContent className="space-y-3">
                  <div className="grid gap-3 sm:grid-cols-[1fr_120px]">
                    <div className="space-y-1.5">
                      <Label className="text-xs">Titlu</Label>
                      <Input value={draft.title} onChange={(e) => setDraft(doc, { title: e.target.value })} />
                    </div>
                    <div className="space-y-1.5">
                      <Label className="text-xs">Ordine</Label>
                      <Input
                        type="number"
                        value={draft.sort_order}
                        onChange={(e) => setDraft(doc, { sort_order: Number(e.target.value) || 0 })}
                      />
                    </div>
                  </div>
                  <div className="space-y-1.5">
                    <Label className="text-xs">Text (body)</Label>
                    <Textarea
                      className="h-64 font-mono text-xs"
                      value={draft.body}
                      onChange={(e) => setDraft(doc, { body: e.target.value })}
                    />
                  </div>
                  <div className="flex items-center justify-between">
                    <p className="text-xs text-muted-foreground">
                      {dirty ? 'Modificări nesalvate' : 'Fără modificări'}
                    </p>
                    <Button
                      size="sm"
                      disabled={!dirty || !draft.title.trim() || pending}
                      onClick={() =>
                        updateMutation.mutate({
                          id: doc.id,
                          payload: {
                            title: draft.title,
                            body: draft.body,
                            sort_order: draft.sort_order,
                            is_active: draft.is_active,
                          },
                        })
                      }
                    >
                      {pending ? 'Se salvează...' : 'Salvează'}
                    </Button>
                  </div>
                </CardContent>
              </Card>
            )
          })}
        </div>
      )}

      <AddDocumentDialog
        open={showAdd}
        onClose={() => setShowAdd(false)}
        onSave={(payload) => createMutation.mutate(payload)}
        isPending={createMutation.isPending}
      />
    </div>
  )
}

function AddDocumentDialog({
  open,
  onClose,
  onSave,
  isPending,
}: {
  open: boolean
  onClose: () => void
  onSave: (payload: CreateConsentDocumentPayload) => void
  isPending: boolean
}) {
  const [docKey, setDocKey] = useState('')
  const [title, setTitle] = useState('')
  const [body, setBody] = useState('')
  const [requiresSignature, setRequiresSignature] = useState(true)
  const [isMandatory, setIsMandatory] = useState(true)

  const resetForm = () => {
    setDocKey('')
    setTitle('')
    setBody('')
    setRequiresSignature(true)
    setIsMandatory(true)
  }

  const handleSave = () => {
    if (!docKey.trim() || !title.trim()) {
      toast.error('Cheia documentului și titlul sunt obligatorii')
      return
    }
    onSave({
      doc_key: docKey.trim(),
      title: title.trim(),
      body,
      requires_signature: requiresSignature,
      is_mandatory: isMandatory,
      is_active: false,
    })
  }

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) onClose(); else resetForm() }}>
      <DialogContent className="sm:max-w-lg" onOpenAutoFocus={resetForm}>
        <DialogHeader>
          <DialogTitle>Document nou</DialogTitle>
          <DialogDescription>
            Documentul se creează inactiv. Activați-l doar după validarea juridică a textului.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label className="text-xs">Cheie document (doc_key) *</Label>
            <Input
              value={docKey}
              onChange={(e) => setDocKey(e.target.value)}
              placeholder="ex: privacy_policy"
              className="font-mono"
            />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Titlu *</Label>
            <Input value={title} onChange={(e) => setTitle(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label className="text-xs">Text (body)</Label>
            <Textarea className="h-40 font-mono text-xs" value={body} onChange={(e) => setBody(e.target.value)} />
          </div>
          <div className="flex flex-wrap items-center gap-4">
            <div className="flex items-center gap-2">
              <Switch checked={requiresSignature} onCheckedChange={setRequiresSignature} />
              <Label className="text-xs">Necesită semnătură</Label>
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={isMandatory} onCheckedChange={setIsMandatory} />
              <Label className="text-xs">Obligatoriu</Label>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Anulează</Button>
          <Button disabled={!docKey.trim() || !title.trim() || isPending} onClick={handleSave}>
            {isPending ? 'Se creează...' : 'Creează'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}
