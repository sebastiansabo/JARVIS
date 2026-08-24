import { Tag, KeyRound } from 'lucide-react'
import { cn } from '@/lib/utils'
import { DOC_TYPE_LABELS, type DocType } from './documentType'

const OPTIONS: { value: DocType; Icon: typeof Tag }[] = [
  { value: 'sales', Icon: Tag },
  { value: 'service', Icon: KeyRound },
]

/** Sales ↔ Service (Mașini de curtoazie) context switch for the standalone
 *  Foi de Parcurs header. Shown only when the company has Service enabled. */
export default function DocTypeToggle({ value, onChange }: { value: DocType; onChange: (v: DocType) => void }) {
  return (
    <div className="flex h-9 shrink-0 gap-0.5 rounded-lg bg-muted p-0.5">
      {OPTIONS.map(({ value: v, Icon }) => (
        <button
          key={v}
          type="button"
          title={DOC_TYPE_LABELS[v]}
          aria-label={DOC_TYPE_LABELS[v]}
          onClick={() => onChange(v)}
          className={cn('flex h-full items-center gap-1.5 rounded-md px-3 text-sm transition-colors',
            value === v ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground')}
        >
          <Icon className="h-4 w-4" />
          <span className="hidden sm:inline">{DOC_TYPE_LABELS[v]}</span>
        </button>
      ))}
    </div>
  )
}
