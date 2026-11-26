import { describe, it, expect } from 'vitest'
import { parseVersionPayload, isNewerBuild } from './versionCheck'

describe('parseVersionPayload', () => {
  it('extracts a string build', () => expect(parseVersionPayload({ build: '123' })).toBe('123'))
  it('null for missing field', () => expect(parseVersionPayload({})).toBeNull())
  it('null for non-object (HTML/text body)', () => expect(parseVersionPayload('<html>')).toBeNull())
  it('null for null/undefined', () => expect(parseVersionPayload(null)).toBeNull())
  it('null for empty-string build', () => expect(parseVersionPayload({ build: '' })).toBeNull())
  it('null for non-string build (e.g. {build: null} from dev route)', () =>
    expect(parseVersionPayload({ build: null })).toBeNull())
})

describe('isNewerBuild', () => {
  it('true when server differs', () => expect(isNewerBuild('100', '200')).toBe(true))
  it('false when equal', () => expect(isNewerBuild('100', '100')).toBe(false))
  it('false when server null', () => expect(isNewerBuild('100', null)).toBe(false))
  it('false when current empty', () => expect(isNewerBuild('', '200')).toBe(false))
})
