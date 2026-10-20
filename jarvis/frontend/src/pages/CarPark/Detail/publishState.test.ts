import { describe, it, expect } from 'vitest'
import { publishPrimaryAction } from './publishState'

describe('publishPrimaryAction', () => {
  it('not_published -> Publică (blue)', () => {
    expect(publishPrimaryAction('not_published')).toEqual({
      label: 'Publică',
      variant: 'default',
      tone: 'blue',
    })
  })

  it('stale -> Actualizează acum (amber)', () => {
    expect(publishPrimaryAction('stale')).toEqual({
      label: 'Actualizează acum',
      variant: 'default',
      tone: 'amber',
    })
  })

  it('up_to_date -> Actualizează (ghost/muted)', () => {
    expect(publishPrimaryAction('up_to_date')).toEqual({
      label: 'Actualizează',
      variant: 'ghost',
      tone: 'muted',
    })
  })

  it('inactive -> Reactivează (blue)', () => {
    expect(publishPrimaryAction('inactive')).toEqual({
      label: 'Reactivează',
      variant: 'default',
      tone: 'blue',
    })
  })

  it('error -> Reîncearcă (amber)', () => {
    expect(publishPrimaryAction('error')).toEqual({
      label: 'Reîncearcă',
      variant: 'default',
      tone: 'amber',
    })
  })

  it('draft -> Actualizează (ghost)', () => {
    expect(publishPrimaryAction('draft')).toEqual({
      label: 'Actualizează',
      variant: 'ghost',
      tone: 'muted',
    })
  })

  it('moderation -> null (no primary)', () => {
    expect(publishPrimaryAction('moderation')).toBeNull()
  })

  it('expired -> null (no primary)', () => {
    expect(publishPrimaryAction('expired')).toBeNull()
  })
})
