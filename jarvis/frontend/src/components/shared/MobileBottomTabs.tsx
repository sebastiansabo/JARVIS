interface MobileBottomTabsProps {
  children: React.ReactNode
}

/** Fixed bottom bar for mobile tab navigation. Always renders — caller should gate with isMobile. */
export function MobileBottomTabs({ children }: MobileBottomTabsProps) {
  return (
    <div className="fixed inset-x-0 bottom-0 z-50 border-t bg-background/95 backdrop-blur px-2 py-1.5 pb-safe">
      {children}
    </div>
  )
}
