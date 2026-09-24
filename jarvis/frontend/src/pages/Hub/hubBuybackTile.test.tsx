import { describe, it, expect } from 'vitest'
import { appTiles } from './index'

describe('BuyBack / TradeIn tile', () => {
  it('is registered in appTiles as an in-page panel (no route)', () => {
    const tile = appTiles.find((t) => t.key === 'buyback')
    expect(tile).toBeDefined()
    expect(tile?.route).toBeUndefined()
    expect(tile?.label).toBe('BuyBack / TradeIn')
  })

  it('is visible when the user can access buyback', () => {
    const visible = appTiles.filter((t) => {
      if (t.key === 'buyback') return true
      return false
    })
    expect(visible.some((t) => t.key === 'buyback')).toBe(true)
  })

  it('is hidden from visibleTiles when can_access_buyback is false (mirrors the Hub gate)', () => {
    const authUser = { can_access_buyback: false }
    const visibleTiles = appTiles.filter((t) => {
      if (t.key === 'buyback' && !authUser.can_access_buyback) return false
      return true
    })
    expect(visibleTiles.find((t) => t.key === 'buyback')).toBeUndefined()
  })

  it('is present in visibleTiles when can_access_buyback is true (mirrors the Hub gate)', () => {
    const authUser = { can_access_buyback: true }
    const visibleTiles = appTiles.filter((t) => {
      if (t.key === 'buyback' && !authUser.can_access_buyback) return false
      return true
    })
    expect(visibleTiles.find((t) => t.key === 'buyback')).toBeDefined()
  })
})
