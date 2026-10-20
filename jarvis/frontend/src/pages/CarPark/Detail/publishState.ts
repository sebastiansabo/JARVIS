import type { Freshness } from './ListingFreshness'

export type PublishPrimaryAction = {
  label: string
  variant: 'default' | 'secondary' | 'ghost'
  tone: 'blue' | 'amber' | 'muted'
}

// Pure state -> primary-action mapping for the publishing panel. One state,
// one obvious next step; moderation/expired have none (nothing the user can
// do from here — moderation resolves itself, expired needs a fresh listing).
const ACTIONS: Record<Freshness, PublishPrimaryAction | null> = {
  not_published: { label: 'Publică', variant: 'default', tone: 'blue' },
  stale: { label: 'Actualizează acum', variant: 'default', tone: 'amber' },
  up_to_date: { label: 'Actualizează', variant: 'ghost', tone: 'muted' },
  inactive: { label: 'Reactivează', variant: 'default', tone: 'blue' },
  error: { label: 'Reîncearcă', variant: 'default', tone: 'amber' },
  draft: { label: 'Actualizează', variant: 'ghost', tone: 'muted' },
  moderation: null,
  expired: null,
}

export function publishPrimaryAction(state: Freshness): PublishPrimaryAction | null {
  return ACTIONS[state]
}
