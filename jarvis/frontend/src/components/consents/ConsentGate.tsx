import { useEffect, useState } from 'react'
import { usePendingConsents, useSignConsent } from '@/hooks/useConsents'
import type { ConsentDocument } from '@/api/consents'
import { ConsentDocumentStep } from './ConsentDocumentStep'

/**
 * Full-screen mandatory-consent blocker. Mounted by Layout (Task 8) above
 * the rest of the app; renders `null` whenever there is nothing to block on
 * so the host can just always render it.
 *
 * `useSignConsent` already invalidates `['currentUser']` on every successful
 * sign, so once the final document is signed we don't need to do anything
 * ourselves to "close" the gate — whatever consumer reads `useAuth()` (the
 * Layout wiring in Task 8) will stop mounting this component once that
 * query refetches with `consents_complete: true`. Until that happens we
 * just show a brief "finishing" state instead of flashing the app behind us.
 */
export default function ConsentGate() {
  const { data, isLoading, isError, refetch } = usePendingConsents(true)
  const signMut = useSignConsent()

  // Freeze the pending list on first load. Signing invalidates
  // ['consents', 'pending'] in the background, which would otherwise
  // reshuffle/shrink the array we're actively stepping through — we track
  // progress locally instead and let the background refetch happen
  // unobserved.
  const [docs, setDocs] = useState<ConsentDocument[] | null>(null)
  const [idx, setIdx] = useState(0)
  const [finishing, setFinishing] = useState(false)

  useEffect(() => {
    if (docs === null && data && data.pending.length > 0) {
      setDocs(data.pending)
    }
  }, [data, docs])

  // Fail closed: if we can't even find out what's pending, keep blocking
  // rather than silently exposing the app.
  if (isError) {
    return (
      <GateShell>
        <p className="text-sm text-white">Nu am putut încărca acordurile necesare.</p>
        <button
          onClick={() => refetch()}
          className="rounded-md bg-white/10 px-4 py-2 text-sm text-white hover:bg-white/20"
        >
          Reîncearcă
        </button>
        <LogoutEscape />
      </GateShell>
    )
  }

  const stillHydrating = isLoading || (!!data && data.pending.length > 0 && docs === null)
  if (stillHydrating) {
    return (
      <GateShell>
        <p className="text-sm text-white">Se încarcă acordurile…</p>
      </GateShell>
    )
  }

  if (finishing || !docs || idx >= docs.length) {
    // Nothing pending from the start (docs stayed null) → nothing to block.
    // Otherwise we're between "last document signed" and the currentUser
    // refetch clearing the gate — keep blocking so the app doesn't flash.
    return docs ? (
      <GateShell>
        <p className="text-sm text-white">Se finalizează…</p>
      </GateShell>
    ) : null
  }

  const doc = docs[idx]

  const handleSign = async (signatureImage: string) => {
    const res = await signMut.mutateAsync({ documentId: doc.id, signatureImage })
    if (res.complete) {
      setFinishing(true)
      return
    }
    setIdx((i) => i + 1)
  }

  return (
    <GateShell>
      <div className="mx-auto flex h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-xl border bg-background shadow-2xl">
        <ConsentDocumentStep
          key={doc.id}
          doc={doc}
          index={idx}
          total={docs.length}
          onSign={handleSign}
          submitting={signMut.isPending}
        />
      </div>
      <LogoutEscape />
    </GateShell>
  )
}

function GateShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-[9999] flex flex-col items-center justify-center gap-4 bg-black/70 p-4 backdrop-blur-sm">
      {children}
    </div>
  )
}

function LogoutEscape() {
  return (
    <a
      href="/logout"
      className="text-sm text-white/70 underline underline-offset-4 hover:text-white"
    >
      Deconectează-te
    </a>
  )
}
