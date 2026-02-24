import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Sparkles, RefreshCw, Clock, Cpu, ChevronDown } from 'lucide-react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { toast } from 'sonner'

import { bilantApi } from '@/api/bilant'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardFooter, CardHeader, CardTitle } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { DropdownMenu, DropdownMenuContent, DropdownMenuItem, DropdownMenuTrigger } from '@/components/ui/dropdown-menu'
import type { BilantAiAnalysis } from '@/types/bilant'

interface AiInsightsCardProps {
  generationId: number
  initialAnalysis?: BilantAiAnalysis | null
}

export function AiInsightsCard({ generationId, initialAnalysis }: AiInsightsCardProps) {
  const [analysis, setAnalysis] = useState<BilantAiAnalysis | null>(initialAnalysis ?? null)
  const [selectedModelId, setSelectedModelId] = useState<number | undefined>(undefined)

  const { data: models } = useQuery({
    queryKey: ['bilant-ai-models'],
    queryFn: bilantApi.getAiModels,
  })

  const selectedModel = models?.find(m => m.id === selectedModelId)
  const defaultModel = models?.find(m => m.is_default)
  const displayModelName = selectedModel?.display_name || defaultModel?.display_name || 'Default'

  const generateMut = useMutation({
    mutationFn: () => bilantApi.getAiAnalysis(generationId, selectedModelId),
    onSuccess: (res) => {
      setAnalysis(res.analysis)
    },
    onError: (err: Error) => {
      toast.error(`AI analysis failed: ${err.message}`)
    },
  })

  const regenerateMut = useMutation({
    mutationFn: async () => {
      await bilantApi.clearAiAnalysis(generationId)
      return bilantApi.getAiAnalysis(generationId, selectedModelId)
    },
    onSuccess: (res) => {
      setAnalysis(res.analysis)
      toast.success('Analysis regenerated')
    },
    onError: (err: Error) => {
      toast.error(`Regeneration failed: ${err.message}`)
    },
  })

  const isLoading = generateMut.isPending || regenerateMut.isPending

  const modelSelector = models && models.length > 1 ? (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="outline" size="sm" className="h-7 text-xs gap-1">
          <Cpu className="h-3 w-3" />
          {displayModelName}
          <ChevronDown className="h-3 w-3" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        {models.map(m => (
          <DropdownMenuItem
            key={m.id}
            onClick={() => setSelectedModelId(m.id)}
            className={m.id === selectedModelId ? 'bg-accent' : ''}
          >
            <span className="mr-2 text-[10px] uppercase text-muted-foreground">{m.provider}</span>
            {m.display_name}
            {m.is_default && <span className="ml-1 text-[10px] text-muted-foreground">(default)</span>}
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  ) : null

  // Not generated yet — show prompt button
  if (!analysis && !isLoading) {
    return (
      <Card className="border-purple-200 dark:border-purple-800/50">
        <CardContent className="flex flex-col items-center justify-center py-8 text-center">
          <Sparkles className="mb-3 h-8 w-8 text-purple-500" />
          <h3 className="mb-1 text-sm font-semibold">AI Financial Analyst</h3>
          <p className="mb-4 max-w-sm text-xs text-muted-foreground">
            Generate AI-powered insights on your financial data — liquidity analysis, risk assessment, and actionable recommendations.
          </p>
          <div className="flex items-center gap-2">
            {modelSelector}
            <Button
              size="sm"
              onClick={() => generateMut.mutate()}
              className="bg-purple-600 hover:bg-purple-700"
            >
              <Sparkles className="mr-1.5 h-3.5 w-3.5" />
              Generate Analysis
            </Button>
          </div>
        </CardContent>
      </Card>
    )
  }

  // Loading state
  if (isLoading) {
    return (
      <Card className="border-purple-200 dark:border-purple-800/50">
        <CardHeader className="pb-3">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Sparkles className="h-4 w-4 text-purple-500 animate-pulse" />
            AI Financial Analyst
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-5/6" />
          <Skeleton className="h-4 w-4/6" />
          <Skeleton className="h-4 w-full" />
          <Skeleton className="h-4 w-3/4" />
          <Skeleton className="h-4 w-5/6" />
        </CardContent>
      </Card>
    )
  }

  // Render analysis
  return (
    <Card className="border-purple-200 dark:border-purple-800/50">
      <CardHeader className="pb-3">
        <div className="flex items-center justify-between">
          <CardTitle className="flex items-center gap-2 text-sm">
            <Sparkles className="h-4 w-4 text-purple-500" />
            AI Financial Analyst
          </CardTitle>
          <div className="flex items-center gap-1">
            {modelSelector}
            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs text-muted-foreground"
              onClick={() => regenerateMut.mutate()}
              disabled={isLoading}
            >
              <RefreshCw className={`mr-1 h-3 w-3 ${regenerateMut.isPending ? 'animate-spin' : ''}`} />
              Regenerate
            </Button>
          </div>
        </div>
      </CardHeader>
      <CardContent className="prose prose-sm dark:prose-invert max-w-none prose-headings:text-sm prose-headings:font-semibold prose-headings:mb-2 prose-headings:mt-4 first:prose-headings:mt-0 prose-p:text-xs prose-p:leading-relaxed prose-li:text-xs prose-ul:my-1 prose-li:my-0.5">
        <ReactMarkdown remarkPlugins={[remarkGfm]}>
          {analysis!.content}
        </ReactMarkdown>
      </CardContent>
      <CardFooter className="pt-0 pb-3">
        <div className="flex items-center gap-4 text-[10px] text-muted-foreground">
          <span className="flex items-center gap-1">
            <Cpu className="h-3 w-3" />
            {analysis!.model}
          </span>
          <span className="flex items-center gap-1">
            <Clock className="h-3 w-3" />
            {new Date(analysis!.generated_at).toLocaleDateString('ro-RO', {
              day: '2-digit', month: '2-digit', year: 'numeric',
              hour: '2-digit', minute: '2-digit',
            })}
          </span>
          <span>{analysis!.input_tokens + analysis!.output_tokens} tokens</span>
        </div>
      </CardFooter>
    </Card>
  )
}
