import { useState } from 'react'
import { X, SlidersHorizontal } from 'lucide-react'
import { Button } from '@/components/ui/button'
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select'
import { Input } from '@/components/ui/input'
import { Sheet, SheetContent, SheetHeader, SheetTitle } from '@/components/ui/sheet'
import { cn } from '@/lib/utils'
import { useIsMobile } from '@/hooks/useMediaQuery'

export interface FilterField {
  key: string
  label: string
  type: 'select' | 'date' | 'text'
  options?: { value: string; label: string }[]
  placeholder?: string
}

interface FilterBarProps {
  fields: FilterField[]
  values: Record<string, string>
  onChange: (values: Record<string, string>) => void
  className?: string
}

function FilterControls({
  fields,
  values,
  onChange,
  vertical,
}: {
  fields: FilterField[]
  values: Record<string, string>
  onChange: (key: string, value: string) => void
  vertical?: boolean
}) {
  return (
    <>
      {fields.map((field) => (
        <div key={field.key} className={vertical ? 'space-y-1' : 'min-w-0'}>
          {vertical && (
            <label className="text-xs font-medium text-muted-foreground">{field.label}</label>
          )}
          {field.type === 'select' ? (
            <Select
              value={values[field.key] || '__all__'}
              onValueChange={(v) => onChange(field.key, v === '__all__' ? '' : v)}
            >
              <SelectTrigger className={vertical ? 'w-full' : 'h-8 w-auto min-w-[120px] gap-1 text-xs'}>
                {!vertical && <span className="text-muted-foreground">{field.label}:</span>}
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="__all__">All</SelectItem>
                {field.options?.map((opt) => (
                  <SelectItem key={opt.value} value={opt.value}>
                    {opt.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          ) : (
            <Input
              type={field.type}
              value={values[field.key] || ''}
              onChange={(e) => onChange(field.key, e.target.value)}
              placeholder={field.placeholder || field.label}
              className={vertical ? 'w-full' : 'h-8 w-auto min-w-[130px] text-xs'}
            />
          )}
        </div>
      ))}
    </>
  )
}

export function FilterBar({ fields, values, onChange, className }: FilterBarProps) {
  const isMobile = useIsMobile()
  const [sheetOpen, setSheetOpen] = useState(false)
  const activeCount = Object.values(values).filter(Boolean).length

  const updateField = (key: string, value: string) => {
    onChange({ ...values, [key]: value })
  }

  const clearAll = () => {
    const cleared: Record<string, string> = {}
    fields.forEach((f) => (cleared[f.key] = ''))
    onChange(cleared)
  }

  if (isMobile) {
    return (
      <>
        <Button
          variant="outline"
          size="sm"
          onClick={() => setSheetOpen(true)}
          className={cn('w-full justify-start', className)}
        >
          <SlidersHorizontal className="mr-2 h-4 w-4" />
          Filters
          {activeCount > 0 && (
            <span className="ml-auto rounded-full bg-primary px-1.5 py-0.5 text-[10px] font-semibold text-primary-foreground">
              {activeCount}
            </span>
          )}
        </Button>
        <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
          <SheetContent side="bottom" className="max-h-[80vh] overflow-y-auto">
            <SheetHeader>
              <SheetTitle>Filters</SheetTitle>
            </SheetHeader>
            <div className="space-y-4 py-4">
              <FilterControls fields={fields} values={values} onChange={updateField} vertical />
              <div className="flex gap-2 pt-2">
                {activeCount > 0 && (
                  <Button variant="outline" size="sm" onClick={clearAll} className="flex-1">
                    <X className="mr-1 h-3 w-3" />
                    Clear All
                  </Button>
                )}
                <Button size="sm" onClick={() => setSheetOpen(false)} className="flex-1">
                  Apply
                </Button>
              </div>
            </div>
          </SheetContent>
        </Sheet>
      </>
    )
  }

  return (
    <div className={cn('flex flex-wrap items-center gap-2', className)}>
      <FilterControls fields={fields} values={values} onChange={updateField} />
      {activeCount > 0 && (
        <Button variant="ghost" size="sm" onClick={clearAll} className="h-8 text-xs text-muted-foreground">
          <X className="mr-1 h-3 w-3" />
          Clear
        </Button>
      )}
    </div>
  )
}
