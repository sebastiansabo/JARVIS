import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { vi, describe, it, expect, beforeEach } from 'vitest'
import Digest from './index'
import { digestApi } from '@/api/digest'

const DM_CHANNEL = {
  id: 7, name: '', description: '', type: 'general', is_private: true,
  allow_member_posts: true, allow_reactions: true, allow_images: true,
  auto_delete_days: null, notify_mode: 'all', created_by: 1, created_by_name: '',
  member_count: 2, post_count: 0, unread_count: 0, avatar_url: null,
  pinned_at: null, archived_at: null, muted: false,
  last_message_content: null, last_message_type: null, last_message_at: null, last_message_author: null,
  is_direct: true, counterpart_user_id: 42, counterpart_name: 'Dana Pop',
  created_at: '', updated_at: '',
}

vi.mock('@/api/digest', () => ({
  digestApi: {
    getChannels: vi.fn(() => Promise.resolve({ success: true, data: [] })),
    searchUsers: vi.fn(() => Promise.resolve({ success: true, data: [
      { id: 42, name: 'Dana Pop', email: 'dana@x.ro', department: 'HR', company: 'AW' },
    ] })),
    openDirect: vi.fn(() => Promise.resolve({ channel: DM_CHANNEL })),
    getPosts: vi.fn(() => Promise.resolve({ success: true, data: [] })),
    markRead: vi.fn(() => Promise.resolve({ success: true })),
  },
}))
vi.mock('@/api/organization', () => ({
  organizationApi: {
    getCompaniesConfig: vi.fn(() => Promise.resolve([])),
    getStructureNodes: vi.fn(() => Promise.resolve([])),
  },
}))

function renderDigest() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(<QueryClientProvider client={qc}><Digest /></QueryClientProvider>)
}

beforeEach(() => {
  vi.clearAllMocks()
  // jsdom doesn't implement scrollIntoView (ChannelView autoscrolls on mount)
  Element.prototype.scrollIntoView = vi.fn()
})

describe('New Direct Message flow', () => {
  it('opens the picker, searches a person, and opens the DM on select', async () => {
    renderDigest()

    // Open the new-message dialog
    fireEvent.click(screen.getByTitle('Mesaj nou'))
    const input = await screen.findByPlaceholderText('Caută o persoană...')

    // Typing (>=2 chars) surfaces the search result
    fireEvent.change(input, { target: { value: 'Da' } })
    const result = await screen.findByText('Dana Pop')

    // Selecting opens the 1:1 via create-or-get
    fireEvent.click(result)
    await waitFor(() => expect(digestApi.openDirect).toHaveBeenCalledWith(42))

    // The view switches to the DM; header shows the counterpart, not a channel name
    expect(await screen.findByRole('heading', { name: 'Dana Pop' })).toBeInTheDocument()
  })

  it('offers new-DM from the Hub (readOnly) but hides group create', async () => {
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(<QueryClientProvider client={qc}><Digest readOnly /></QueryClientProvider>)
    // DM creation must be reachable from the Hub (widely used surface)
    expect(await screen.findByTitle('Mesaj nou')).toBeInTheDocument()
    // Channel creation stays management-only (sidebar)
    expect(screen.queryByText('Canal nou')).not.toBeInTheDocument()
  })
})
