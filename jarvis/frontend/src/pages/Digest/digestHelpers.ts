import type { DigestChannel } from '@/types/digest'

export type ChatFilter = 'all' | 'unread' | 'direct' | 'groups'

/** Client-side conversation-list filter. 'direct' = 1:1 DMs, 'groups' = everything else. */
export function filterChannels(channels: DigestChannel[], filter: ChatFilter): DigestChannel[] {
  switch (filter) {
    case 'unread':
      return channels.filter(c => c.unread_count > 0)
    case 'direct':
      return channels.filter(c => c.is_direct)
    case 'groups':
      return channels.filter(c => !c.is_direct)
    default:
      return channels
  }
}

/** Display title for a conversation row/header: the counterpart for a DM, else the channel name. */
export function channelTitle(ch: DigestChannel): string {
  if (ch.is_direct) return ch.counterpart_name || 'Conversație'
  return ch.name
}

/** Two-letter initials from a display name (e.g. "Dana Pop" → "DP"). */
export function nameInitials(name: string): string {
  return name
    .split(' ')
    .map(n => n[0])
    .join('')
    .slice(0, 2)
    .toUpperCase()
}

/** Two-letter avatar initials derived from the display title. */
export function channelInitials(ch: DigestChannel): string {
  return nameInitials(channelTitle(ch))
}
