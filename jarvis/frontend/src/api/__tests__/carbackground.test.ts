import { describe, it, expect, vi } from 'vitest'
import { carbackgroundApi } from '../carbackground'
import { api } from '../client'

describe('carbackgroundApi', () => {
  it('getConfig calls GET /carbackground/api/config', async () => {
    const get = vi.spyOn(api, 'get').mockResolvedValue({
      success: true,
      configured: true,
      connector: { has_api_key: true, background_id: 'studio-white', api_base_url: '' },
    } as any)
    await carbackgroundApi.getConfig()
    expect(get).toHaveBeenCalledWith('/carbackground/api/config')
  })

  it('saveConfig calls POST /carbackground/api/config with the payload', async () => {
    const post = vi.spyOn(api, 'post').mockResolvedValue({
      success: true,
      config: { configured: true, has_api_key: true, background_id: 'bg-2' },
    } as any)
    await carbackgroundApi.saveConfig({ api_key: 'secret', background_id: 'bg-2' })
    expect(post).toHaveBeenCalledWith('/carbackground/api/config', {
      api_key: 'secret',
      background_id: 'bg-2',
    })
  })

  it('listBackgrounds calls GET /carbackground/api/backgrounds', async () => {
    const get = vi.spyOn(api, 'get').mockResolvedValue({ success: true, backgrounds: [] } as any)
    await carbackgroundApi.listBackgrounds()
    expect(get).toHaveBeenCalledWith('/carbackground/api/backgrounds')
  })

  it('credits calls GET /carbackground/api/credits', async () => {
    const get = vi.spyOn(api, 'get').mockResolvedValue({ success: true, balance: 42 } as any)
    await carbackgroundApi.credits()
    expect(get).toHaveBeenCalledWith('/carbackground/api/credits')
  })

  it('enhance posts the selected photo ids to the vehicle enhance route', async () => {
    const post = vi
      .spyOn(api, 'post')
      .mockResolvedValue({ success: true, created: 2, errors: [] } as any)
    const res = await carbackgroundApi.enhance(9, [1, 2])
    expect(post).toHaveBeenCalledWith('/carbackground/api/vehicles/9/enhance', {
      photo_ids: [1, 2],
    })
    expect(res.created).toBe(2)
  })

  it('setPublished calls PUT /carbackground/api/photos/:id/publish', async () => {
    const put = vi.spyOn(api, 'put').mockResolvedValue({ success: true, published: true } as any)
    await carbackgroundApi.setPublished(5, true)
    expect(put).toHaveBeenCalledWith('/carbackground/api/photos/5/publish', { published: true })
  })

  it('deleteEnhanced calls DELETE /carbackground/api/photos/:id/enhanced', async () => {
    const del = vi.spyOn(api, 'delete').mockResolvedValue({ success: true } as any)
    await carbackgroundApi.deleteEnhanced(5)
    expect(del).toHaveBeenCalledWith('/carbackground/api/photos/5/enhanced')
  })
})
