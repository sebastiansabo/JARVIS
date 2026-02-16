import { memo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { Bot, User } from 'lucide-react'
import { cn } from '@/lib/utils'
import type { Message } from '@/types/aiAgent'

interface MessageBubbleProps {
  message: Message
}

const markdownComponents = {
  pre: ({ children }: { children?: React.ReactNode }) => (
    <pre className="overflow-x-auto rounded-md bg-background/50 p-3 text-xs">
      {children}
    </pre>
  ),
  code: ({ className, children, ...props }: { className?: string; children?: React.ReactNode }) => {
    const isInline = !className
    return isInline ? (
      <code className="rounded bg-background/50 px-1 py-0.5 text-xs" {...props}>
        {children}
      </code>
    ) : (
      <code className={className} {...props}>
        {children}
      </code>
    )
  },
}

const remarkPlugins = [remarkGfm]

export const MessageBubble = memo(function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === 'user'

  return (
    <div className={cn('flex gap-3', isUser && 'flex-row-reverse')}>
      <div
        className={cn(
          'flex h-8 w-8 shrink-0 items-center justify-center rounded-full',
          isUser ? 'bg-primary text-primary-foreground' : 'bg-muted'
        )}
      >
        {isUser ? <User className="h-4 w-4" /> : <Bot className="h-4 w-4" />}
      </div>

      <div className={cn('max-w-[80%] space-y-1', isUser && 'items-end')}>
        <div
          className={cn(
            'rounded-lg px-4 py-2',
            isUser ? 'bg-primary text-primary-foreground' : 'bg-muted'
          )}
        >
          {isUser ? (
            <p className="whitespace-pre-wrap text-sm">{message.content}</p>
          ) : (
            <div className="prose prose-sm dark:prose-invert max-w-none">
              <ReactMarkdown
                remarkPlugins={remarkPlugins}
                components={markdownComponents}
              >
                {message.content}
              </ReactMarkdown>
            </div>
          )}
        </div>

        {message.role === 'assistant' && (message.response_time_ms > 0 || message.output_tokens > 0) && (
          <div className={cn('flex gap-2 text-xs text-muted-foreground', isUser && 'justify-end')}>
            {message.response_time_ms > 0 && <span>{(message.response_time_ms / 1000).toFixed(1)}s</span>}
            {message.output_tokens > 0 && <span>{message.output_tokens} tokens</span>}
            {message.cost && Number(message.cost) > 0 && <span>${message.cost}</span>}
          </div>
        )}
      </div>
    </div>
  )
})
