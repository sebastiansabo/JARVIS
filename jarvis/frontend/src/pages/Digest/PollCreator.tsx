import { useState } from 'react'
import { Plus, X } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Switch } from '@/components/ui/switch'

interface Props {
  onSubmit: (question: string, options: string[], isMultiple: boolean) => void
  onCancel: () => void
  isPending: boolean
}

export default function PollCreator({ onSubmit, onCancel, isPending }: Props) {
  const [question, setQuestion] = useState('')
  const [options, setOptions] = useState(['', ''])
  const [isMultiple, setIsMultiple] = useState(false)

  const addOption = () => {
    if (options.length < 10) setOptions([...options, ''])
  }

  const removeOption = (idx: number) => {
    if (options.length > 2) setOptions(options.filter((_, i) => i !== idx))
  }

  const updateOption = (idx: number, value: string) => {
    setOptions(options.map((o, i) => (i === idx ? value : o)))
  }

  const validOptions = options.filter((o) => o.trim())
  const canSubmit = question.trim() && validOptions.length >= 2

  return (
    <div className="rounded-lg border p-4 space-y-3 bg-card">
      <div className="flex items-center justify-between">
        <Label className="text-sm font-semibold">Create Poll</Label>
        <Button variant="ghost" size="icon" className="h-6 w-6" onClick={onCancel}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      <Input
        placeholder="Ask a question..."
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
      />

      <div className="space-y-2">
        {options.map((opt, idx) => (
          <div key={idx} className="flex items-center gap-2">
            <Input
              placeholder={`Option ${idx + 1}`}
              value={opt}
              onChange={(e) => updateOption(idx, e.target.value)}
            />
            {options.length > 2 && (
              <Button variant="ghost" size="icon" className="h-8 w-8 shrink-0" onClick={() => removeOption(idx)}>
                <X className="h-3.5 w-3.5" />
              </Button>
            )}
          </div>
        ))}
        {options.length < 10 && (
          <Button variant="outline" size="sm" onClick={addOption}>
            <Plus className="h-3.5 w-3.5 mr-1" /> Add option
          </Button>
        )}
      </div>

      <div className="flex items-center gap-2">
        <Switch checked={isMultiple} onCheckedChange={setIsMultiple} />
        <Label className="text-xs">Allow multiple selections</Label>
      </div>

      <div className="flex justify-end gap-2">
        <Button variant="outline" size="sm" onClick={onCancel}>Cancel</Button>
        <Button
          size="sm"
          disabled={!canSubmit || isPending}
          onClick={() => onSubmit(question, validOptions, isMultiple)}
        >
          Post Poll
        </Button>
      </div>
    </div>
  )
}
