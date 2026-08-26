import { describe, it, expect } from 'vitest'
import { sessionParty, buildUserPhoneMap, clientCell } from './sessionParty'
import type { FoiContract } from '@/types/foiParcurs'

const c = (over: Partial<FoiContract>) => over as FoiContract

describe('clientCell (who the Client column shows — the person who drives)', () => {
  it('company booking: the driver is primary, the company is the secondary line', () => {
    expect(clientCell(c({ client_name: 'VINUM PARTIUM SRL', driver_name: 'Calin Gonta' })))
      .toEqual({ primary: 'Calin Gonta', secondary: 'VINUM PARTIUM SRL' })
  })
  it('person booking (driver == client): just the person, no secondary', () => {
    expect(clientCell(c({ client_name: 'Ion Pop', driver_name: 'Ion Pop' })))
      .toEqual({ primary: 'Ion Pop', secondary: null })
  })
  it('no driver on file: shows the client, no secondary', () => {
    expect(clientCell(c({ client_name: 'VINUM PARTIUM SRL', driver_name: null })))
      .toEqual({ primary: 'VINUM PARTIUM SRL', secondary: null })
  })
  it('internal log: the driving user (advisor) is the party', () => {
    expect(clientCell(c({ is_internal: true, advisor_name: 'Patrasc Roger', driver_name: null })))
      .toEqual({ primary: 'Patrasc Roger', secondary: null })
  })
  it('neither client nor driver: dash', () => {
    expect(clientCell(c({ client_name: null, client_id: null, driver_name: null })))
      .toEqual({ primary: '—', secondary: null })
  })
})

describe('buildUserPhoneMap', () => {
  it('maps lower-cased user name → phone', () => {
    const m = buildUserPhoneMap([
      { name: 'Pop Marius', phone: '0711' },
      { name: 'Ana Ionescu', phone: null },
    ])
    expect(m.get('pop marius')).toBe('0711')
    expect(m.get('ana ionescu')).toBeNull()
  })

  it('trims names and ignores blank ones', () => {
    const m = buildUserPhoneMap([
      { name: '  Calin Gonta  ', phone: '072' },
      { name: '', phone: '000' },
    ])
    expect(m.get('calin gonta')).toBe('072')
    expect(m.has('')).toBe(false)
  })
})

describe('sessionParty (normal Test Drive)', () => {
  it('shows the client name + phone under a Client label', () => {
    const p = sessionParty(c({ client_name: 'Ion Pop', client_phone: '0740' }))
    expect(p).toMatchObject({ isInternal: false, label: 'Client', name: 'Ion Pop', phone: '0740' })
  })

  it('falls back to "Client #id" when only client_id is set', () => {
    const p = sessionParty(c({ client_id: 42, client_name: null }))
    expect(p.name).toBe('Client #42')
  })

  it('shows a dash when there is neither name nor id', () => {
    const p = sessionParty(c({ client_name: null, client_id: null }))
    expect(p.name).toBe('—')
    expect(p.phone).toBe('—')
  })
})

describe('sessionParty (internal driving log)', () => {
  const usersByPhone = buildUserPhoneMap([{ name: 'Patrasc Roger', phone: '0755123456' }])

  it('uses the driving user (advisor_name) as the party under a "Șofer" label', () => {
    const p = sessionParty(c({ is_internal: true, client_name: null, advisor_name: 'Patrasc Roger' }), usersByPhone)
    expect(p).toMatchObject({ isInternal: true, label: 'Șofer', name: 'Patrasc Roger' })
  })

  it('resolves the driver phone from the Users directory (name match)', () => {
    const p = sessionParty(c({ is_internal: true, advisor_name: 'Patrasc Roger' }), usersByPhone)
    expect(p.phone).toBe('0755123456')
  })

  it('shows a dash phone when the driver is not a known user', () => {
    const p = sessionParty(c({ is_internal: true, advisor_name: 'Cineva Necunoscut' }), usersByPhone)
    expect(p.phone).toBe('—')
  })
})
