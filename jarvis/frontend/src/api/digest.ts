import { api } from './client'
import type { ApiResponse } from '@/types'
import type { DigestChannel, DigestPost, DigestPoll, DigestMember, DigestUnreadCount, DigestChannelTarget, DigestUserSearchResult } from '@/types/digest'

export const digestApi = {
  // Channels
  getChannels: (params?: { q?: string; archived?: boolean }) => {
    const sp: Record<string, string> = {}
    if (params?.q) sp.q = params.q
    if (params?.archived) sp.archived = '1'
    return api.get<ApiResponse<DigestChannel[]>>('/api/chat/channels', sp)
  },

  getChannel: (channelId: number) =>
    api.get<ApiResponse<DigestChannel>>(`/api/chat/channels/${channelId}`),

  createChannel: (data: {
    name: string
    description?: string
    type?: string
    is_private?: boolean
    targets?: { target_type: string; company_id?: number; node_id?: number }[]
  }) =>
    api.post<ApiResponse<DigestChannel>>('/api/chat/channels', data),

  updateChannel: (channelId: number, data: { name: string; description?: string }) =>
    api.put<ApiResponse<DigestChannel>>(`/api/chat/channels/${channelId}`, data),

  deleteChannel: (channelId: number) =>
    api.delete<ApiResponse>(`/api/chat/channels/${channelId}`),

  // Per-user conversation state (pin / archive / mute)
  setChannelPinned: (channelId: number, pinned: boolean) =>
    api.put<ApiResponse>(`/api/chat/channels/${channelId}/pin`, { pinned }),

  setChannelArchived: (channelId: number, archived: boolean) =>
    api.put<ApiResponse>(`/api/chat/channels/${channelId}/archive`, { archived }),

  setChannelMuted: (channelId: number, muted: boolean) =>
    api.put<ApiResponse>(`/api/chat/channels/${channelId}/mute`, { muted }),

  // Channel Targets
  getChannelTargets: (channelId: number) =>
    api.get<ApiResponse<DigestChannelTarget[]>>(`/api/chat/channels/${channelId}/targets`),

  updateChannelTargets: (channelId: number, targets: { target_type: string; company_id?: number; node_id?: number }[]) =>
    api.put<ApiResponse>(`/api/chat/channels/${channelId}/targets`, { targets }),

  // Channel Settings
  updateChannelSettings: (channelId: number, settings: Partial<{
    name: string
    description: string
    type: string
    is_private: boolean
    allow_member_posts: boolean
    allow_reactions: boolean
    allow_images: boolean
    auto_delete_days: number | null
    notify_mode: string
    avatar_url: string | null
  }>) =>
    api.put<ApiResponse<DigestChannel>>(`/api/chat/channels/${channelId}/settings`, settings),

  clearChannelHistory: (channelId: number) =>
    api.post<ApiResponse>(`/api/chat/channels/${channelId}/clear-history`),

  // Members
  getMembers: (channelId: number) =>
    api.get<ApiResponse<DigestMember[]>>(`/api/chat/channels/${channelId}/members`),

  addMember: (channelId: number, userId: number, role?: string) =>
    api.post<ApiResponse<DigestMember>>(`/api/chat/channels/${channelId}/members`, { user_id: userId, role }),

  removeMember: (channelId: number, userId: number) =>
    api.delete<ApiResponse>(`/api/chat/channels/${channelId}/members/${userId}`),

  setMemberRole: (channelId: number, userId: number, role: string) =>
    api.put<ApiResponse>(`/api/chat/channels/${channelId}/members/${userId}/role`, { role }),

  // User Search
  searchUsers: (q: string) =>
    api.get<ApiResponse<DigestUserSearchResult[]>>(`/api/chat/users/search`, { q }),

  // Posts
  getPosts: (channelId: number, params?: { limit?: number; offset?: number; parent_id?: number }) => {
    const searchParams: Record<string, string> = {}
    if (params?.limit) searchParams.limit = String(params.limit)
    if (params?.offset) searchParams.offset = String(params.offset)
    if (params?.parent_id) searchParams.parent_id = String(params.parent_id)
    return api.get<ApiResponse<DigestPost[]>>(`/api/chat/channels/${channelId}/posts`, searchParams)
  },

  getPost: (postId: number) =>
    api.get<ApiResponse<DigestPost>>(`/api/chat/posts/${postId}`),

  createPost: (channelId: number, data: {
    content: string
    type?: string
    parent_id?: number
    reply_to_id?: number
    poll?: { question: string; options: string[]; is_multiple_choice?: boolean; closes_at?: string }
  }) =>
    api.post<ApiResponse<DigestPost>>(`/api/chat/channels/${channelId}/posts`, data),

  updatePost: (postId: number, content: string) =>
    api.put<ApiResponse<DigestPost>>(`/api/chat/posts/${postId}`, { content }),

  deletePost: (postId: number) =>
    api.delete<ApiResponse>(`/api/chat/posts/${postId}`),

  togglePin: (postId: number) =>
    api.post<ApiResponse<DigestPost>>(`/api/chat/posts/${postId}/pin`),

  // Reactions
  toggleReaction: (postId: number, emoji: string) =>
    api.post<ApiResponse<{ action: 'added' | 'removed' }>>(`/api/chat/posts/${postId}/reactions`, { emoji }),

  // Polls
  getPoll: (postId: number) =>
    api.get<ApiResponse<DigestPoll>>(`/api/chat/posts/${postId}/poll`),

  vote: (pollId: number, optionId: number) =>
    api.post<ApiResponse>(`/api/chat/polls/${pollId}/vote`, { option_id: optionId }),

  unvote: (pollId: number, optionId: number) =>
    api.post<ApiResponse>(`/api/chat/polls/${pollId}/unvote`, { option_id: optionId }),

  // Read status
  markRead: (channelId: number, postId: number) =>
    api.post<ApiResponse>(`/api/chat/channels/${channelId}/read`, { post_id: postId }),

  getUnreadCounts: () =>
    api.get<ApiResponse<DigestUnreadCount[]>>('/api/chat/unread'),
}
