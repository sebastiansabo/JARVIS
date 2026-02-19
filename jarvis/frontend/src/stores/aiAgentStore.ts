import { create } from 'zustand'

interface AiAgentState {
  selectedModel: string | null
  isWidgetOpen: boolean
  setModel: (model: string | null) => void
  toggleWidget: () => void
  setWidgetOpen: (open: boolean) => void
}

export const useAiAgentStore = create<AiAgentState>((set) => ({
  selectedModel: null,
  isWidgetOpen: false,
  setModel: (model) => set({ selectedModel: model }),
  toggleWidget: () => set((s) => ({ isWidgetOpen: !s.isWidgetOpen })),
  setWidgetOpen: (open) => set({ isWidgetOpen: open }),
}))
