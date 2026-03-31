export interface DigestChannel {
  id: number
  name: string
  description: string
  type: 'general' | 'announcement' | 'department'
  is_private: boolean
  allow_member_posts: boolean
  allow_reactions: boolean
  allow_images: boolean
  auto_delete_days: number | null
  notify_mode: 'all' | 'mentions_polls' | 'mute'
  created_by: number
  created_by_name: string
  member_count: number
  post_count: number
  unread_count: number
  created_at: string
  updated_at: string
}

export interface DigestChannelTarget {
  id: number
  channel_id: number
  target_type: 'all' | 'company' | 'node'
  company_id: number | null
  node_id: number | null
  node_name: string | null
  node_level: number | null
  company_name: string | null
}

export interface DigestPost {
  id: number
  channel_id: number
  user_id: number
  user_name: string
  content: string
  type: 'post' | 'announcement' | 'poll'
  is_pinned: boolean
  parent_id: number | null
  reply_to_id: number | null
  reply_to_post_id: number | null
  reply_to_content: string | null
  reply_to_user_name: string | null
  reply_count: number
  reactions: DigestReaction[]
  poll?: DigestPoll
  created_at: string
  updated_at: string
}

export interface DigestReaction {
  emoji: string
  count: number
  user_names: string[]
  user_ids: number[]
}

export interface DigestPoll {
  id: number
  post_id: number
  question: string
  is_multiple_choice: boolean
  closes_at: string | null
  options: DigestPollOption[]
  total_votes: number
  user_votes?: number[]
}

export interface DigestPollOption {
  id: number
  poll_id: number
  option_text: string
  sort_order: number
  vote_count: number
}

export interface DigestMember {
  id: number
  channel_id: number
  user_id: number
  user_name: string
  user_email: string
  role: 'admin' | 'moderator' | 'member'
  joined_at: string
}

export interface DigestUnreadCount {
  channel_id: number
  name: string
  unread_count: number
}

export interface DigestUserSearchResult {
  id: number
  name: string
  email: string
  department: string | null
  company: string | null
}
