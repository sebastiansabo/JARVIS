import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Settings2, ChevronUp, ChevronDown, RotateCcw } from 'lucide-react'
import { WIDGET_CATALOG, type WidgetPref } from './types'
import { cn } from '@/lib/utils'

interface Props {
  permittedWidgets: WidgetPref[]
  toggleWidget: (id: string) => void
  moveWidget: (id: string, direction: 'up' | 'down') => void
  resetDefaults: () => void
}

export function CustomizeSheet({ permittedWidgets, toggleWidget, moveWidget, resetDefaults }: Props) {
  const catalogMap = new Map(WIDGET_CATALOG.map(w => [w.id, w]))

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline" size="sm">
          <Settings2 className="mr-1.5 h-4 w-4" />
          Customize
        </Button>
      </SheetTrigger>
      <SheetContent className="w-[340px] sm:w-[380px]">
        <SheetHeader>
          <SheetTitle>Customize Dashboard</SheetTitle>
        </SheetHeader>
        <div className="mt-4 space-y-1">
          {permittedWidgets.map((wp, idx) => {
            const def = catalogMap.get(wp.id)
            if (!def) return null
            const Icon = def.icon
            return (
              <div
                key={wp.id}
                className={cn(
                  'flex items-center gap-3 rounded-md border px-3 py-2',
                  !wp.visible && 'opacity-50',
                )}
              >
                <Switch
                  checked={wp.visible}
                  onCheckedChange={() => toggleWidget(wp.id)}
                  className="scale-90"
                />
                <Icon className="h-4 w-4 text-muted-foreground shrink-0" />
                <span className="text-sm font-medium flex-1">{def.name}</span>
                <div className="flex gap-0.5">
                  <button
                    type="button"
                    onClick={() => moveWidget(wp.id, 'up')}
                    disabled={idx === 0}
                    className="p-1 rounded hover:bg-accent disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    <ChevronUp className="h-3.5 w-3.5" />
                  </button>
                  <button
                    type="button"
                    onClick={() => moveWidget(wp.id, 'down')}
                    disabled={idx === permittedWidgets.length - 1}
                    className="p-1 rounded hover:bg-accent disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    <ChevronDown className="h-3.5 w-3.5" />
                  </button>
                </div>
              </div>
            )
          })}
        </div>
        <div className="mt-4 pt-4 border-t">
          <Button variant="ghost" size="sm" onClick={resetDefaults} className="w-full">
            <RotateCcw className="mr-1.5 h-3.5 w-3.5" />
            Reset to Defaults
          </Button>
        </div>
      </SheetContent>
    </Sheet>
  )
}
