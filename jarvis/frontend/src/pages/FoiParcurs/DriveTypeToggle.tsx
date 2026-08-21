import { List, User, Building2 } from 'lucide-react'
import { cn } from '@/lib/utils'

export type DriveType = 'all' | 'client' | 'internal'

const OPTIONS = [
  { value: 'all', label: 'Toate', Icon: List },
  { value: 'client', label: 'Client', Icon: User },
  { value: 'internal', label: 'Intern', Icon: Building2 },
] as const

/** Icon-only Client ↔ internal drive filter, shown on the Sesiuni + Calendar
 *  tabs' toolbar row. Labels are dropped (title/aria-label carry them). */
export default function DriveTypeToggle({ value, onChange }: { value: DriveType; onChange: (v: DriveType) => void }) {
  return (
    <div className="flex h-8 shrink-0 gap-0.5 rounded-lg bg-muted p-0.5">
      {OPTIONS.map(({ value: v, label, Icon }) => (
        <button
          key={v}
          type="button"
          title={label}
          aria-label={label}
          onClick={() => onChange(v)}
          className={cn('flex h-full w-8 items-center justify-center rounded-md transition-colors', value === v ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground')}
        >
          <Icon className="h-4 w-4" />
        </button>
      ))}
    </div>
  )
}
