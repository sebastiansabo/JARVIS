import { api } from './client'
import type { ApiResponse } from '@/types'
import type { DigestChannel, DigestPost, DigestPoll, DigestMember, DigestUnreadCount, DigestChannelTarget, DigestUserSearchResult } from '@/types/digest'

export const digestApi = {
  // Channels
  getChannels: () =>
    api.get<ApiResponse<DigestChannel[]>>('/api/digest/channels'),

  getChannel: (channelId: number) =>
    api.get<ApiResponse<DigestChannel>>(`/api/digest/channels/${channelId}`),

  createChannel: (data: {
    name: string
    description?: string
    type?: string
    is_private?: boolean
    targets?: { target_type: string; company_id?: number; node_id?: number }[]
  }) =>
    api.post<ApiResponse<DigestChannel>>('/api/digest/channels', data),

  updateChannel: (channelId: number, data: { name: string; description?: string }) =>
    api.put<ApiResponse<DigestChannel>>(`/api/digest/channels/${channelId}`, data),

  deleteChannel: (channelId: number) =>
    api.delete<ApiResponse>(`/api/digest/channels/${channelId}`),

  // Channel Targets
  getChannelTargets: (channelId: number) =>
    api.get<ApiResponse<DigestChannelTarget[]>>(`/api/digest/channels/${channelId}/targets`),

  updateChannelTargets: (channelId: number, targets: { target_type: string; company_id?: number; node_id?: number }[]) =>
    api.put<ApiResponse>(`/api/digest/channels/${channelId}/targets`, { targets }),

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
  }>) =>
    api.put<ApiResponse<DigestChannel>>(`/api/digest/channels/${channelId}/settings`, settings),

  clearChannelHistory: (channelId: number) =>
    api.post<ApiResponse>(`/api/digest/channels/${channelId}/clear-history`),

  // Members
  getMembers: (channelId: number) =>
    api.get<ApiResponse<DigestMember[]>>(`/api/digest/channels/${channelId}/members`),

  addMember: (channelId: number, userId: number, role?: string) =>
    api.post<ApiResponse<DigestMember>>(`/api/digest/channels/${channelId}/members`, { user_id: userId, role }),

  removeMember: (channelId: number, userId: number) =>
    api.delete<ApiResponse>(`/api/digest/channels/${channelId}/members/${userId}`),

  setMemberRole: (channelId: number, userId: number, role: string) =>
    api.put<ApiResponse>(`/api/digest/channels/${channelId}/members/${userId}/role`, { role }),

  // User Search
  searchUsers: (q: string) =>
    api.get<ApiResponse<DigestUserSearchResult[]>>(`/api/digest/users/search`, { q }),

  // Posts
  getPosts: (channelId: number, params?: { limit?: number; offset?: number; parent_id?: number }) => {
    const searchParams: Record<string, string> = {}
    if (params?.limit) searchParams.limit = String(params.limit)
    if (params?.offset) searchParams.offset = String(params.offset)
    if (params?.parent_id) searchParams.parent_id = String(params.parent_id)
    return api.get<ApiResponse<DigestPost[]>>(`/api/digest/channels/${channelId}/posts`, searchParams)
  },

  getPost: (postId: number) =>
    api.get<ApiResponse<DigestPost>>(`/api/digest/posts/${postId}`),

  createPost: (channelId: number, data: {
    content: string
    type?: string
    parent_id?: number
    reply_to_id?: number
    poll?: { question: string; options: string[]; is_multiple_choice?: boolean; closes_at?: string }
  }) =>
    api.post<ApiResponse<DigestPost>>(`/api/digest/channels/${channelId}/posts`, data),

  updatePost: (postId: number, content: string) =>
    api.put<ApiResponse<DigestPost>>(`/api/digest/posts/${postId}`, { content }),

  deletePost: (postId: number) =>
    api.delete<ApiResponse>(`/api/digest/posts/${postId}`),

  togglePin: (postId: number) =>
    api.post<ApiResponse<DigestPost>>(`/api/digest/posts/${postId}/pin`),

  // Reactions
  toggleReaction: (postId: number, emoji: string) =>
    api.post<ApiResponse<{ action: 'added' | 'removed' }>>(`/api/digest/posts/${postId}/reactions`, { emoji }),

  // Polls
  getPoll: (postId: number) =>
    api.get<ApiResponse<DigestPoll>>(`/api/digest/posts/${postId}/poll`),

  vote: (pollId: number, optionId: number) =>
    api.post<ApiResponse>(`/api/digest/polls/${pollId}/vote`, { option_id: optionId }),

  unvote: (pollId: number, optionId: number) =>
    api.post<ApiResponse>(`/api/digest/polls/${pollId}/unvote`, { option_id: optionId }),

  // Read status
  markRead: (channelId: number, postId: number) =>
    api.post<ApiResponse>(`/api/digest/channels/${channelId}/read`, { post_id: postId }),

  getUnreadCounts: () =>
    api.get<ApiResponse<DigestUnreadCount[]>>('/api/digest/unread'),
}
