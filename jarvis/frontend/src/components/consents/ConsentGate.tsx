import { useEffect, useRef, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { usePendingConsents, useSignConsent } from '@/hooks/useConsents'
import type { ConsentDocument } from '@/api/consents'
import { ConsentDocumentStep } from './ConsentDocumentStep'

/**
 * Full-screen mandatory-consent blocker. Mounted by Layout (Task 8) above
 * the rest of the app whenever `user.consents_complete === false`.
 *
 * `useSignConsent` already invalidates `['currentUser']` on every successful
 * sign, so once the final document is signed we don't need to do anything
 * ourselves to "close" the gate — whatever consumer reads `useAuth()` (the
 * Layout wiring in Task 8) will stop mounting this component once that
 * query refetches with `consents_complete: true`. Until that happens we
 * just show a brief "finishing" state instead of flashing the app behind us.
 *
 * Fix (final whole-branch review, fix wave 1): this component must NEVER
 * render a bare blank screen while it's mounted — every branch renders
 * inside `GateShell` with a `LogoutEscape`, so a user can never get stuck
 * with no way out. If `GET /api/consents/pending` resolves with an EMPTY
 * list at mount (stale `['currentUser']` cache said `consents_complete:
 * false` but there's actually nothing pending — e.g. an admin deactivated
 * the docs, or they were already signed on another device), `docs` would
 * otherwise stay `null` forever and the terminal branch below used to
 * return bare `null` — a permanently blank page with `user.consents_complete`
 * never re-checked. We self-heal that case by invalidating `['currentUser']`
 * exactly once so Layout re-evaluates and unmounts us if we're really done.
 */
export default function ConsentGate() {
  const { data, isLoading, isError, refetch } = usePendingConsents(true)
  const signMut = useSignConsent()
  const queryClient = useQueryClient()
  const selfHealedRef = useRef(false)

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

  // Self-heal, once: if the pending query has resolved (not loading, not
  // errored) with an empty list — whether that's true at mount (docs never
  // got frozen) or becomes true later via the background refetch — nudge
  // Layout to re-check by invalidating the current-user query. Guarded by a
  // ref so this can only ever fire once per mount: no refetch/render loop.
  useEffect(() => {
    if (!selfHealedRef.current && !isLoading && !isError && data && data.pending.length === 0) {
      selfHealedRef.current = true
      queryClient.invalidateQueries({ queryKey: ['currentUser'] })
    }
  }, [data, isLoading, isError, queryClient])

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
    // Either: nothing pending from the start (docs stayed null — the
    // self-heal effect above is already invalidating currentUser so Layout
    // re-checks); or we're between "last document signed" and the
    // currentUser refetch clearing the gate; or a frozen `docs` list got
    // exhausted without a fresh document count matching (e.g. an admin
    // activated a new mandatory doc mid-onboarding). In every case: keep
    // blocking (never flash the app), but ALWAYS render inside the shell
    // with a logout escape — never a bare blank screen.
    return (
      <GateShell>
        <p className="text-sm text-white">Se finalizează…</p>
        <LogoutEscape />
      </GateShell>
    )
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
