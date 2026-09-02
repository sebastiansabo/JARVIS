import { useEffect, useRef, useState } from 'react'
import SignatureCanvas from '@/components/shared/SignatureCanvas'
import { Checkbox } from '@/components/ui/checkbox'
import { Button } from '@/components/ui/button'
import { Progress } from '@/components/ui/progress'
import type { ConsentDocument } from '@/api/consents'

// How close to the bottom (px) counts as "reached the end" of the body.
const SCROLL_END_THRESHOLD_PX = 24

interface ConsentDocumentStepProps {
  doc: ConsentDocument
  index: number
  total: number
  onSign: (signaturePng: string) => void
  submitting: boolean
}

export function ConsentDocumentStep({ doc, index, total, onSign, submitting }: ConsentDocumentStepProps) {
  const [scrolledEnd, setScrolledEnd] = useState(false)
  const [agreed, setAgreed] = useState(false)
  const [signature, setSignature] = useState('')
  const bodyRef = useRef<HTMLDivElement>(null)

  const checkScrolledEnd = () => {
    const el = bodyRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < SCROLL_END_THRESHOLD_PX
    if (atBottom) setScrolledEnd(true)
  }

  // Short bodies that never overflow the panel can't fire a scroll event —
  // check once on mount (per document) so they don't permanently block.
  useEffect(() => {
    checkScrolledEnd()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [doc.id])

  const canSubmit = agreed && !!signature && !submitting

  return (
    <div className="flex h-full flex-col">
      <div className="border-b px-6 py-4">
        <div className="flex items-center justify-between gap-3">
          <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
            Document {index + 1} din {total}
          </p>
          <p className="text-xs text-muted-foreground">v{doc.version}</p>
        </div>
        <Progress value={((index + 1) / total) * 100} className="mt-2 h-1.5" />
        <h2 className="mt-3 text-lg font-semibold leading-tight">{doc.title}</h2>
      </div>

      <div
        ref={bodyRef}
        onScroll={checkScrolledEnd}
        data-testid="consent-body"
        className="mx-6 my-4 flex-1 overflow-y-auto whitespace-pre-wrap rounded-md border bg-muted/30 p-4 text-sm leading-relaxed"
      >
        {doc.body}
      </div>

      <div className="space-y-3 border-t px-6 py-4">
        <label className="flex items-start gap-2 text-sm">
          <Checkbox
            checked={agreed}
            disabled={!scrolledEnd}
            onCheckedChange={(checked) => setAgreed(checked === true)}
            className="mt-0.5"
          />
          <span>
            Am citit și sunt de acord cu „{doc.title}”.
            {!scrolledEnd && (
              <em className="mt-1 block text-xs not-italic text-muted-foreground">
                Derulați documentul până la final pentru a continua.
              </em>
            )}
          </span>
        </label>

        <SignatureCanvas
          onSave={setSignature}
          onClear={() => setSignature('')}
          disabled={submitting}
          saveLabel="Confirmă semnătura"
        />

        <Button className="w-full" disabled={!canSubmit} onClick={() => onSign(signature)}>
          {submitting ? 'Se salvează…' : 'Semnează și continuă'}
        </Button>
      </div>
    </div>
  )
}
