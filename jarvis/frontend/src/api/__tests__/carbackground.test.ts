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

  it('enhance queues the selected photo ids and returns the job', async () => {
    const post = vi
      .spyOn(api, 'post')
      .mockResolvedValue({ success: true, queued: 2, job_id: 7 } as any)
    const res = await carbackgroundApi.enhance(9, [1, 2])
    expect(post).toHaveBeenCalledWith('/carbackground/api/vehicles/9/enhance', {
      photo_ids: [1, 2],
    })
    expect(res.queued).toBe(2)
    expect(res.job_id).toBe(7)
  })

  it('enhance includes background_id when a background is chosen', async () => {
    const post = vi
      .spyOn(api, 'post')
      .mockResolvedValue({ success: true, queued: 1, job_id: 1 } as any)
    await carbackgroundApi.enhance(9, [1], 'grey-concrete')
    expect(post).toHaveBeenCalledWith('/carbackground/api/vehicles/9/enhance', {
      photo_ids: [1],
      background_id: 'grey-concrete',
    })
  })

  it('enhance omits background_id when none is chosen', async () => {
    const post = vi
      .spyOn(api, 'post')
      .mockResolvedValue({ success: true, queued: 1, job_id: 1 } as any)
    await carbackgroundApi.enhance(9, [1])
    expect(post.mock.calls[0][1]).not.toHaveProperty('background_id')
  })

  it('enhanceStatus GETs the per-vehicle job status', async () => {
    const get = vi.spyOn(api, 'get').mockResolvedValue({
      success: true, running: true, total: 7, done: 3, created: 3, errors: [], background_id: 'x',
    } as any)
    const res = await carbackgroundApi.enhanceStatus(9)
    expect(get).toHaveBeenCalledWith('/carbackground/api/vehicles/9/enhance/status')
    expect(res.running).toBe(true)
    expect(res.done).toBe(3)
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
