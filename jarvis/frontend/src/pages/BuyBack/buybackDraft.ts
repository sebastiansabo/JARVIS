/**
 * Local (per-browser) autosave for the BuyBack intake form's CREATE flow.
 *
 * Drafts are keyed per-user so a second account on the same machine never sees
 * the first's in-progress intake. Photos are deliberately NOT persisted — they
 * are base64 data-URLs that would blow localStorage's ~5MB quota; only the
 * text/select fields are saved. All access is best-effort: localStorage may be
 * unavailable (privacy mode / SSR) and must never throw into the form.
 *
 * Shared by the web route form and the Hub overlay (both render the same
 * BuyBackForm component).
 */

const DRAFT_PREFIX = 'buyback.draft.v1.'

// Fields excluded from the saved draft and from the "has the user entered
// anything?" dirtiness check: images (too big — see above) and the advisor,
// which the form auto-fills from the logged-in user on mount (so it must not,
// on its own, count as user-entered content or every fresh form would look
// dirty and keep re-saving an otherwise-empty draft).
const EXCLUDED_KEYS = ['images', 'advisor_id', 'advisor_name'] as const

type FormLike = Record<string, unknown>

export function draftKey(userId: number | string | null | undefined): string {
  return `${DRAFT_PREFIX}${userId ?? 'anon'}`
}

// `object` (not FormLike) so typed form interfaces without an index signature
// (e.g. BuyBackFormState) are accepted at the call sites.
function stripExcluded(form: object): FormLike {
  const copy: FormLike = { ...(form as FormLike) }
  for (const k of EXCLUDED_KEYS) delete copy[k]
  return copy
}

/** True when the form holds user-entered content beyond the auto-filled
 *  advisor (i.e. worth persisting / differs from a pristine empty form). */
export function isDraftDirty(form: object, emptyForm: object): boolean {
  return JSON.stringify(stripExcluded(form)) !== JSON.stringify(stripExcluded(emptyForm))
}

export function loadDraft<T = FormLike>(userId: number | string | null | undefined): T | null {
  try {
    const raw = localStorage.getItem(draftKey(userId))
    return raw ? (JSON.parse(raw) as T) : null
  } catch {
    return null
  }
}

/** Persist the form minus the excluded (photo/advisor) keys. */
export function saveDraft(userId: number | string | null | undefined, form: object): void {
  try {
    localStorage.setItem(draftKey(userId), JSON.stringify(stripExcluded(form)))
  } catch {
    /* quota exceeded / unavailable — autosave is best-effort */
  }
}

export function clearDraft(userId: number | string | null | undefined): void {
  try {
    localStorage.removeItem(draftKey(userId))
  } catch {
    /* ignore */
  }
}
