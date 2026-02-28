import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from '@/components/ui/sheet'
import { Button } from '@/components/ui/button'
import { Switch } from '@/components/ui/switch'
import { Settings2, RotateCcw } from 'lucide-react'
import { WIDGET_CATALOG, type WidgetPref } from './types'
import { cn } from '@/lib/utils'

interface Props {
  permittedWidgets: WidgetPref[]
  toggleWidget: (id: string) => void
  setWidgetWidth: (id: string, width: number) => void
  resetDefaults: () => void
}

const WIDTH_OPTIONS = [1, 2, 3, 4, 5, 6] as const

export function CustomizeSheet({ permittedWidgets, toggleWidget, setWidgetWidth, resetDefaults }: Props) {
  const catalogMap = new Map(WIDGET_CATALOG.map(w => [w.id, w]))

  return (
    <Sheet>
      <SheetTrigger asChild>
        <Button variant="outline" size="icon" className="md:size-auto md:px-3">
          <Settings2 className="h-4 w-4 md:mr-1.5" />
          <span className="hidden md:inline">Customize</span>
        </Button>
      </SheetTrigger>
      <SheetContent className="w-[340px] sm:w-[380px]">
        <SheetHeader>
          <SheetTitle>Customize Dashboard</SheetTitle>
        </SheetHeader>
        <p className="mt-2 text-xs text-muted-foreground">Toggle visibility and set column width. Drag widgets on the dashboard to reposition.</p>
        <div className="mt-4 space-y-1">
          {permittedWidgets.map((wp) => {
            const def = catalogMap.get(wp.id)
            if (!def) return null
            const Icon = def.icon
            const currentW = wp.layout?.w ?? def.defaultLayout.w
            return (
              <div
                key={wp.id}
                className={cn(
                  'rounded-md border px-3 py-2 space-y-2',
                  !wp.visible && 'opacity-50',
                )}
              >
                <div className="flex items-center gap-3">
                  <Switch
                    checked={wp.visible}
                    onCheckedChange={() => toggleWidget(wp.id)}
                    className="scale-90"
                  />
                  <Icon className="h-4 w-4 text-muted-foreground shrink-0" />
                  <span className="text-sm font-medium flex-1">{def.name}</span>
                </div>
                {wp.visible && (
                  <div className="flex items-center gap-1 pl-10">
                    <span className="text-xs text-muted-foreground mr-1">Width:</span>
                    {WIDTH_OPTIONS.map(w => (
                      <button
                        key={w}
                        type="button"
                        onClick={() => setWidgetWidth(wp.id, w)}
                        className={cn(
                          'h-6 w-6 rounded text-xs font-medium transition-colors',
                          w === currentW
                            ? 'bg-primary text-primary-foreground'
                            : 'bg-muted hover:bg-accent',
                        )}
                      >
                        {w}
                      </button>
                    ))}
                  </div>
                )}
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
