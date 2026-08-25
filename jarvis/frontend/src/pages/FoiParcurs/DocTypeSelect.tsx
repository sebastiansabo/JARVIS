import { Tag, KeyRound } from 'lucide-react'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import type { DocType, DocumentType } from './documentType'

/** Document-type context switch for the standalone Foi de Parcurs header — a
 *  dropdown of the company's active types (Vânzări / Mașini de curtoazie / …).
 *  Shown only when the company has more than one active type. */
export default function DocTypeSelect({ value, types, onChange }: {
  value: DocType
  types: Pick<DocumentType, 'key' | 'label' | 'is_rental'>[]
  onChange: (v: DocType) => void
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="h-9 w-auto min-w-[180px] gap-1.5 rounded-lg" aria-label="Tip document">
        <SelectValue />
      </SelectTrigger>
      <SelectContent>
        {types.map((t) => (
          <SelectItem key={t.key} value={t.key}>
            <span className="flex items-center gap-1.5">
              {t.is_rental ? <KeyRound className="h-4 w-4" /> : <Tag className="h-4 w-4" />}
              {t.label}
            </span>
          </SelectItem>
        ))}
      </SelectContent>
    </Select>
  )
}
