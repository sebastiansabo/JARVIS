import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { digestApi } from '@/api/digest'
import { cn } from '@/lib/utils'
import type { DigestPoll } from '@/types/digest'

interface Props {
  poll: DigestPoll
  channelId: number
}

export default function PollDisplay({ poll, channelId }: Props) {
  const queryClient = useQueryClient()

  // Fetch fresh poll data with user votes
  const { data: pollRes } = useQuery({
    queryKey: ['digest-poll', poll.post_id],
    queryFn: () => digestApi.getPoll(poll.post_id),
    initialData: { success: true, data: poll },
  })
  const p = pollRes?.data ?? poll
  const userVotes = p.user_votes ?? []

  const voteMutation = useMutation({
    mutationFn: (optionId: number) => {
      if (userVotes.includes(optionId)) {
        return digestApi.unvote(p.id, optionId)
      }
      return digestApi.vote(p.id, optionId)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['digest-poll', poll.post_id] })
      queryClient.invalidateQueries({ queryKey: ['digest-posts', channelId] })
    },
  })

  const isClosed = p.closes_at && new Date(p.closes_at) < new Date()

  return (
    <div className="mt-2 rounded-lg border p-3 space-y-2 max-w-md">
      <div className="text-sm font-medium">{p.question}</div>
      {p.is_multiple_choice && (
        <p className="text-[10px] text-muted-foreground">Select multiple options</p>
      )}
      <div className="space-y-1.5">
        {p.options.map((opt) => {
          const pct = p.total_votes > 0 ? Math.round((opt.vote_count / p.total_votes) * 100) : 0
          const hasVoted = userVotes.includes(opt.id)
          return (
            <button
              key={opt.id}
              onClick={() => !isClosed && voteMutation.mutate(opt.id)}
              disabled={isClosed || voteMutation.isPending}
              className={cn(
                'relative w-full rounded-md border px-3 py-1.5 text-left text-sm transition-colors overflow-hidden',
                hasVoted ? 'border-primary' : 'hover:bg-accent',
                isClosed && 'cursor-default',
              )}
            >
              {/* Progress bar bg */}
              <div
                className={cn(
                  'absolute inset-y-0 left-0 transition-all duration-300',
                  hasVoted ? 'bg-primary/15' : 'bg-muted',
                )}
                style={{ width: `${pct}%` }}
              />
              <div className="relative flex items-center justify-between">
                <span className={hasVoted ? 'font-medium' : ''}>{opt.option_text}</span>
                <span className="text-xs text-muted-foreground ml-2">{pct}%</span>
              </div>
            </button>
          )
        })}
      </div>
      <p className="text-[11px] text-muted-foreground">
        {p.total_votes} {p.total_votes === 1 ? 'vote' : 'votes'}
        {isClosed && ' · Poll closed'}
      </p>
    </div>
  )
}
