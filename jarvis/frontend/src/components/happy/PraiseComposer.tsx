import { useState } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'sonner'
import { Search, X } from 'lucide-react'
import { Dialog, DialogContent, DialogTitle } from '@/components/ui/dialog'
import { Sheet, SheetContent, SheetTitle } from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Textarea } from '@/components/ui/textarea'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { useIsMobile } from '@/hooks/useMediaQuery'
import { cn } from '@/lib/utils'
import { ApiError } from '@/api/client'
import { praiseApi } from '@/api/happy'
import { digestApi } from '@/api/digest'
import type { HappyKudosVisibility } from '@/types/happy'

export const MIN_NOTE_LENGTH = 40

/** Pure gate for the submit button — recipient + value tag + a ≥40-char note. */
export function canSubmitKudos(input: {
  recipientId: number | null
  valueTagId: number | null
  note: string
  submitting?: boolean
}): boolean {
  return (
    !!input.recipientId &&
    !!input.valueTagId &&
    input.note.trim().length >= MIN_NOTE_LENGTH &&
    !input.submitting
  )
}

/** Server 400 `code` → Romanian, user-facing message. */
const ERROR_MESSAGES: Record<string, string> = {
  duplicate_text: 'Scrie ceva specific — nota seamănă prea mult cu una recentă.',
  cap_exceeded: 'Ai atins limita de 3 aprecieri către această persoană luna aceasta.',
  insufficient_giveable: 'Nu mai ai puncte de oferit luna aceasta.',
  note_too_short: 'Nota trebuie să aibă cel puțin 40 de caractere.',
  self_award: 'Nu îți poți oferi apreciere ție.',
  value_tag_required: 'Alege o valoare.',
  invalid_points: 'Număr de puncte invalid.',
  invalid_visibility: 'Vizibilitate invalidă.',
}

const VISIBILITY_LABELS: Record<HappyKudosVisibility, string> = {
  company: 'Toată compania',
  department: 'Departamentul meu',
  private: 'Doar destinatarul',
}

interface Recipient {
  id: number
  name: string
}

interface ComposerBodyProps {
  TitleWrapper: React.ComponentType<{ className?: string; children?: React.ReactNode }>
  onClose: () => void
}

function ComposerBody({ TitleWrapper, onClose }: ComposerBodyProps) {
  const queryClient = useQueryClient()
  const [recipient, setRecipient] = useState<Recipient | null>(null)
  const [search, setSearch] = useState('')
  const [valueTagId, setValueTagId] = useState<number | null>(null)
  const [note, setNote] = useState('')
  const [visibility, setVisibility] = useState<HappyKudosVisibility>('company')
  const [submitting, setSubmitting] = useState(false)

  const { data: tagsRes } = useQuery({
    queryKey: ['happy', 'praise', 'value-tags'],
    queryFn: () => praiseApi.getValueTags(),
    staleTime: 5 * 60_000,
  })
  const valueTags = tagsRes?.value_tags ?? []

  const { data: searchRes } = useQuery({
    queryKey: ['happy', 'praise', 'user-search', search],
    queryFn: () => digestApi.searchUsers(search),
    enabled: !recipient && search.trim().length >= 2,
  })
  const searchResults = searchRes?.data ?? []

  const noteLen = note.trim().length
  const canSubmit = canSubmitKudos({ recipientId: recipient?.id ?? null, valueTagId, note, submitting })

  const handleSubmit = async () => {
    if (!recipient || !valueTagId || !canSubmit) return
    setSubmitting(true)
    try {
      await praiseApi.sendKudos({
        to_user: recipient.id,
        value_tag_id: valueTagId,
        note: note.trim(),
        visibility,
      })
      toast.success('Apreciere trimisă.')
      queryClient.invalidateQueries({ queryKey: ['happy', 'praise'] })
      onClose()
    } catch (err) {
      const code = err instanceof ApiError ? (err.data as { code?: string } | null)?.code : undefined
      toast.error((code && ERROR_MESSAGES[code]) || 'Nu am putut trimite aprecierea.')
      setSubmitting(false)
    }
  }

  return (
    <div className="space-y-4">
      <TitleWrapper className="text-lg font-semibold">Trimite o apreciere</TitleWrapper>

      {/* Recipient */}
      <div className="space-y-1.5">
        <Label>Către</Label>
        {recipient ? (
          <div className="flex items-center justify-between rounded-md border px-3 py-2 text-sm">
            <span className="truncate font-medium">{recipient.name}</span>
            <Button
              variant="ghost"
              size="icon-xs"
              aria-label="Schimbă destinatarul"
              onClick={() => {
                setRecipient(null)
                setSearch('')
              }}
            >
              <X className="h-3.5 w-3.5" />
            </Button>
          </div>
        ) : (
          <div className="space-y-1">
            <div className="relative">
              <Search className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Caută un coleg…"
                className="pl-8"
              />
            </div>
            {search.trim().length >= 2 && searchResults.length > 0 && (
              <div className="max-h-40 overflow-y-auto rounded-md border">
                {searchResults.map((u) => (
                  <button
                    key={u.id}
                    type="button"
                    onClick={() => {
                      setRecipient({ id: u.id, name: u.name })
                      setSearch('')
                    }}
                    className="flex w-full flex-col items-start px-3 py-2 text-left text-sm transition-colors hover:bg-accent/50"
                  >
                    <span className="font-medium">{u.name}</span>
                    {(u.department || u.company) && (
                      <span className="text-xs text-muted-foreground">
                        {[u.department, u.company].filter(Boolean).join(' · ')}
                      </span>
                    )}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Value tag */}
      <div className="space-y-1.5">
        <Label>Valoare</Label>
        <Select
          value={valueTagId ? String(valueTagId) : undefined}
          onValueChange={(v) => setValueTagId(Number(v))}
        >
          <SelectTrigger>
            <SelectValue placeholder="Alege o valoare" />
          </SelectTrigger>
          <SelectContent>
            {valueTags.map((t) => (
              <SelectItem key={t.id} value={String(t.id)}>
                <span className="flex items-center gap-2">
                  {t.icon && <span aria-hidden>{t.icon}</span>}
                  {t.label_ro}
                </span>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Note */}
      <div className="space-y-1.5">
        <Label htmlFor="praise-note">Mesaj</Label>
        <Textarea
          id="praise-note"
          value={note}
          onChange={(e) => setNote(e.target.value)}
          placeholder="Spune concret ce a făcut și de ce contează…"
          rows={4}
        />
        <p
          className={cn(
            'text-xs',
            noteLen >= MIN_NOTE_LENGTH ? 'text-muted-foreground' : 'text-destructive',
          )}
        >
          {noteLen}/{MIN_NOTE_LENGTH} caractere
        </p>
      </div>

      {/* Visibility */}
      <div className="space-y-1.5">
        <Label>Vizibilitate</Label>
        <Select value={visibility} onValueChange={(v) => setVisibility(v as HappyKudosVisibility)}>
          <SelectTrigger>
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {(Object.keys(VISIBILITY_LABELS) as HappyKudosVisibility[]).map((v) => (
              <SelectItem key={v} value={v}>
                {VISIBILITY_LABELS[v]}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {/* Actions */}
      <div className="flex flex-col-reverse gap-2 pt-1 sm:flex-row sm:justify-end">
        <Button variant="ghost" onClick={onClose}>
          Anulează
        </Button>
        <Button disabled={!canSubmit} onClick={handleSubmit}>
          Trimite apreciere
        </Button>
      </div>
    </div>
  )
}

export interface PraiseComposerProps {
  open: boolean
  onOpenChange: (open: boolean) => void
}

/**
 * Send-kudos composer. Desktop = Dialog, mobile = bottom Sheet. Note must be
 * ≥40 chars (client-gated, server-enforced). Recipient search reuses the existing
 * colleague search (`digestApi.searchUsers` → /api/chat/users/search).
 */
export function PraiseComposer({ open, onOpenChange }: PraiseComposerProps) {
  const isMobile = useIsMobile()
  const close = () => onOpenChange(false)

  // Remount the body on each open so form state always starts clean.
  if (!open) {
    return isMobile ? (
      <Sheet open={false} onOpenChange={onOpenChange} />
    ) : (
      <Dialog open={false} onOpenChange={onOpenChange} />
    )
  }

  if (isMobile) {
    return (
      <Sheet open={open} onOpenChange={onOpenChange}>
        <SheetContent side="bottom" className="max-h-[92vh] overflow-y-auto rounded-t-3xl">
          <div className="px-1 pb-2">
            <ComposerBody TitleWrapper={SheetTitle} onClose={close} />
          </div>
        </SheetContent>
      </Sheet>
    )
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-[520px]">
        <ComposerBody TitleWrapper={DialogTitle} onClose={close} />
      </DialogContent>
    </Dialog>
  )
}

export default PraiseComposer
