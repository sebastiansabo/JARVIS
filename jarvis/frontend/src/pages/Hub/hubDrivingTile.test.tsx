import { describe, it, expect } from 'vitest'
import { appTiles } from './index'

describe('Driving Sessions tile', () => {
  it('is registered in appTiles as an in-page panel (no route)', () => {
    const tile = appTiles.find((t) => t.key === 'driving')
    expect(tile).toBeDefined()
    expect(tile?.route).toBeUndefined()
    expect(tile?.label).toBe('Driving Sessions')
  })
})
