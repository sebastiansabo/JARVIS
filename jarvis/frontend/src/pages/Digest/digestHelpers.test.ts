import { describe, it, expect } from 'vitest'
import { filterChannels, channelTitle, channelInitials } from './digestHelpers'
import type { DigestChannel } from '@/types/digest'

const mk = (o: Partial<DigestChannel>): DigestChannel => ({
  id: 1, name: 'Grup', description: '', type: 'general', is_private: false,
  allow_member_posts: true, allow_reactions: true, allow_images: true,
  auto_delete_days: null, notify_mode: 'all', created_by: 1, created_by_name: '',
  member_count: 2, post_count: 0, unread_count: 0, avatar_url: null,
  pinned_at: null, archived_at: null, muted: false,
  last_message_content: null, last_message_type: null, last_message_at: null, last_message_author: null,
  is_direct: false, counterpart_user_id: null, counterpart_name: null,
  created_at: '', updated_at: '',
  ...o,
})

describe('filterChannels', () => {
  const chans = [
    mk({ id: 1, is_direct: false, unread_count: 0 }),
    mk({ id: 2, is_direct: true, counterpart_name: 'Dana', unread_count: 3 }),
    mk({ id: 3, is_direct: false, unread_count: 1 }),
  ]
  it('all returns everything', () => expect(filterChannels(chans, 'all').map(c => c.id)).toEqual([1, 2, 3]))
  it('unread returns only unread', () => expect(filterChannels(chans, 'unread').map(c => c.id)).toEqual([2, 3]))
  it('direct returns only DMs', () => expect(filterChannels(chans, 'direct').map(c => c.id)).toEqual([2]))
  it('groups returns only non-DMs', () => expect(filterChannels(chans, 'groups').map(c => c.id)).toEqual([1, 3]))
})

describe('channelTitle / channelInitials', () => {
  it('DM uses the counterpart name', () => {
    const dm = mk({ is_direct: true, counterpart_name: 'Dana Pop', name: '' })
    expect(channelTitle(dm)).toBe('Dana Pop')
    expect(channelInitials(dm)).toBe('DP')
  })
  it('group uses the channel name', () => {
    const g = mk({ is_direct: false, name: 'Suport Jarvis' })
    expect(channelTitle(g)).toBe('Suport Jarvis')
    expect(channelInitials(g)).toBe('SJ')
  })
  it('DM with no counterpart falls back gracefully', () => {
    const dm = mk({ is_direct: true, counterpart_name: null, name: '' })
    expect(channelTitle(dm)).toBe('Conversație')
  })
})
