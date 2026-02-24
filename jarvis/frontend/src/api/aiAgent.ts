import { api } from './client'
import type { Conversation, ConversationDetail, ChatResponse, Model, StreamDoneEvent } from '@/types/aiAgent'

export const aiAgentApi = {
  getConversations: async (): Promise<Conversation[]> => {
    const data = await api.get<{ conversations: Conversation[] }>('/ai-agent/api/conversations')
    return data.conversations
  },

  createConversation: (title?: string) =>
    api.post<Conversation>('/ai-agent/api/conversations', title ? { title } : {}),

  getConversation: async (id: number): Promise<ConversationDetail> => {
    const data = await api.get<{ conversation: Conversation; messages: ConversationDetail['messages'] }>(
      `/ai-agent/api/conversations/${id}`,
    )
    return { ...data.conversation, messages: data.messages }
  },

  archiveConversation: (id: number) =>
    api.post<{ success: boolean }>(`/ai-agent/api/conversations/${id}/archive`, {}),

  deleteConversation: (id: number) =>
    api.delete<{ success: boolean }>(`/ai-agent/api/conversations/${id}`),

  sendMessage: (conversationId: number, content: string, modelConfigId?: string) =>
    api.post<ChatResponse>('/ai-agent/api/chat', {
      conversation_id: conversationId,
      message: content,
      ...(modelConfigId && { model_config_id: Number(modelConfigId) }),
    }),

  getModels: async (): Promise<Model[]> => {
    const data = await api.get<{ models: Model[] }>('/ai-agent/api/models')
    return data.models
  },

  streamMessage: async (
    conversationId: number,
    content: string,
    modelConfigId: string | undefined,
    onChunk: (text: string) => void,
    onDone: (data: StreamDoneEvent) => void,
    onError: (error: string) => void,
    onStatus?: (status: string) => void,
  ) => {
    const response = await fetch('/ai-agent/api/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({
        conversation_id: conversationId,
        message: content,
        ...(modelConfigId && { model_config_id: Number(modelConfigId) }),
      }),
    })

    if (response.status === 401) {
      window.location.href = '/login'
      return
    }

    if (!response.ok || !response.body) {
      onError('Failed to connect to stream')
      return
    }

    const reader = response.body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })

      // Parse SSE events from buffer
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      let eventType = ''
      for (const line of lines) {
        if (line.startsWith('event: ')) {
          eventType = line.slice(7)
        } else if (line.startsWith('data: ')) {
          const data = line.slice(6)
          try {
            const parsed = JSON.parse(data)
            if (eventType === 'token') {
              onChunk(parsed.content)
            } else if (eventType === 'done') {
              onDone(parsed)
            } else if (eventType === 'error') {
              onError(parsed.error)
            } else if (eventType === 'status') {
              onStatus?.(parsed.status)
            }
          } catch {
            // skip malformed JSON
          }
          eventType = ''
        }
      }
    }
  },

  getRagStats: () =>
    api.get<{ total_documents: number; total_chunks: number }>('/ai-agent/api/rag/stats'),
}
