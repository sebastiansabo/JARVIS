import { useState, useEffect, useMemo, useCallback } from 'react'
import type { User } from '@/types'
import { WIDGET_CATALOG, type DashboardPreferences } from './types'

const STORAGE_KEY = 'jarvis_dashboard_prefs'
const CURRENT_VERSION = 1

function hasPermission(user: User | null, permission?: keyof User): boolean {
  if (!permission) return true
  return !!user?.[permission]
}

function buildDefaults(): DashboardPreferences {
  return {
    version: CURRENT_VERSION,
    widgets: WIDGET_CATALOG.map((w, i) => ({
      id: w.id,
      visible: w.defaultVisible,
      order: i,
    })),
  }
}

function loadPrefs(): DashboardPreferences {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (!raw) return buildDefaults()
    const parsed = JSON.parse(raw) as DashboardPreferences
    if (parsed.version !== CURRENT_VERSION) return buildDefaults()
    // Ensure any new widgets are added
    const existing = new Set(parsed.widgets.map(w => w.id))
    const maxOrder = Math.max(0, ...parsed.widgets.map(w => w.order))
    let nextOrder = maxOrder + 1
    for (const def of WIDGET_CATALOG) {
      if (!existing.has(def.id)) {
        parsed.widgets.push({ id: def.id, visible: def.defaultVisible, order: nextOrder++ })
      }
    }
    // Remove widgets no longer in catalog
    const catalogIds = new Set(WIDGET_CATALOG.map(w => w.id))
    parsed.widgets = parsed.widgets.filter(w => catalogIds.has(w.id))
    return parsed
  } catch {
    return buildDefaults()
  }
}

export function useDashboardPrefs(user: User | null) {
  const [prefs, setPrefs] = useState<DashboardPreferences>(loadPrefs)

  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(prefs))
  }, [prefs])

  const permittedWidgets = useMemo(() => {
    const catalogMap = new Map(WIDGET_CATALOG.map(w => [w.id, w]))
    return prefs.widgets
      .filter(w => {
        const def = catalogMap.get(w.id)
        return def && hasPermission(user, def.permission)
      })
      .sort((a, b) => a.order - b.order)
  }, [prefs, user])

  const visibleWidgets = useMemo(() => {
    return permittedWidgets.filter(w => w.visible)
  }, [permittedWidgets])

  const toggleWidget = useCallback((id: string) => {
    setPrefs(prev => ({
      ...prev,
      widgets: prev.widgets.map(w =>
        w.id === id ? { ...w, visible: !w.visible } : w,
      ),
    }))
  }, [])

  const moveWidget = useCallback((id: string, direction: 'up' | 'down') => {
    setPrefs(prev => {
      const sorted = [...prev.widgets].sort((a, b) => a.order - b.order)
      const idx = sorted.findIndex(w => w.id === id)
      if (idx < 0) return prev
      const swapIdx = direction === 'up' ? idx - 1 : idx + 1
      if (swapIdx < 0 || swapIdx >= sorted.length) return prev
      const temp = sorted[idx].order
      sorted[idx] = { ...sorted[idx], order: sorted[swapIdx].order }
      sorted[swapIdx] = { ...sorted[swapIdx], order: temp }
      return { ...prev, widgets: sorted }
    })
  }, [])

  const resetDefaults = useCallback(() => {
    setPrefs(buildDefaults())
  }, [])

  const isVisible = useCallback((id: string) => {
    return visibleWidgets.some(w => w.id === id)
  }, [visibleWidgets])

  return { permittedWidgets, visibleWidgets, toggleWidget, moveWidget, resetDefaults, isVisible }
}
