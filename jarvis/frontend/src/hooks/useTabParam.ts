import { useState, useCallback } from 'react'
import { useSearchParams } from 'react-router-dom'

/**
 * Like useState but persists the value in the URL search param `?tab=xxx`.
 * On page refresh the tab is restored from the URL.
 */
export function useTabParam<T extends string>(defaultTab: T, paramName = 'tab'): [T, (tab: T) => void] {
  const [searchParams, setSearchParams] = useSearchParams()
  const initial = (searchParams.get(paramName) as T) || defaultTab
  const [tab, setTabState] = useState<T>(initial)

  const setTab = useCallback((next: T) => {
    setTabState(next)
    setSearchParams((prev) => {
      const p = new URLSearchParams(prev)
      if (next === defaultTab) {
        p.delete(paramName)
      } else {
        p.set(paramName, next)
      }
      return p
    }, { replace: true })
  }, [defaultTab, paramName, setSearchParams])

  return [tab, setTab]
}
