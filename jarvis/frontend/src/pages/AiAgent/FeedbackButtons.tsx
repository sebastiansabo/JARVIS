import { useState } from 'react'
import { ThumbsUp, ThumbsDown } from 'lucide-react'
import { cn } from '@/lib/utils'
import { aiAgentApi } from '@/api/aiAgent'

interface FeedbackButtonsProps {
  messageId: number
}

export function FeedbackButtons({ messageId }: FeedbackButtonsProps) {
  const [feedback, setFeedback] = useState<'positive' | 'negative' | null>(null)
  const [loading, setLoading] = useState(false)

  const handleFeedback = async (type: 'positive' | 'negative') => {
    if (loading) return
    setLoading(true)
    try {
      const result = await aiAgentApi.submitFeedback(messageId, type)
      setFeedback(result.feedback ? result.feedback.feedback_type as 'positive' | 'negative' : null)
    } catch {
      // silently fail
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="flex items-center gap-1">
      <button
        onClick={() => handleFeedback('positive')}
        disabled={loading}
        className={cn(
          'rounded p-1 transition-colors hover:bg-muted',
          feedback === 'positive' ? 'text-green-500' : 'text-muted-foreground/50 hover:text-muted-foreground'
        )}
        title="Helpful"
      >
        <ThumbsUp className={cn('h-3.5 w-3.5', feedback === 'positive' && 'fill-current')} />
      </button>
      <button
        onClick={() => handleFeedback('negative')}
        disabled={loading}
        className={cn(
          'rounded p-1 transition-colors hover:bg-muted',
          feedback === 'negative' ? 'text-red-500' : 'text-muted-foreground/50 hover:text-muted-foreground'
        )}
        title="Not helpful"
      >
        <ThumbsDown className={cn('h-3.5 w-3.5', feedback === 'negative' && 'fill-current')} />
      </button>
    </div>
  )
}
