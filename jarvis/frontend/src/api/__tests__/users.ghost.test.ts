import { describe, it, expect, vi } from 'vitest'
import { usersApi } from '../users'
import { api } from '../client'

describe('usersApi ghost', () => {
  it('setGhost calls PUT /api/users/:id/ghost', async () => {
    const put = vi.spyOn(api, 'put').mockResolvedValue({ success: true, is_ghost: true } as any)
    await usersApi.setGhost(5, true)
    expect(put).toHaveBeenCalledWith('/api/users/5/ghost', { is_ghost: true })
  })
  it('canManageGhosts calls GET', async () => {
    const get = vi.spyOn(api, 'get').mockResolvedValue({ can_manage_ghosts: true } as any)
    await usersApi.canManageGhosts()
    expect(get).toHaveBeenCalledWith('/api/users/can-manage-ghosts')
  })
})
