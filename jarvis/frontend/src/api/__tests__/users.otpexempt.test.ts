import { describe, it, expect, vi } from 'vitest'
import { usersApi } from '../users'
import { api } from '../client'

describe('usersApi otp-exempt', () => {
  it('setOtpExempt calls PUT /api/users/:id/otp-exempt with the flag', async () => {
    const put = vi.spyOn(api, 'put').mockResolvedValue({ success: true, otp_exempt: true } as any)
    await usersApi.setOtpExempt(5, true)
    expect(put).toHaveBeenCalledWith('/api/users/5/otp-exempt', { otp_exempt: true })
  })

  it('setOtpExempt can re-enable OTP (false)', async () => {
    const put = vi.spyOn(api, 'put').mockResolvedValue({ success: true, otp_exempt: false } as any)
    await usersApi.setOtpExempt(9, false)
    expect(put).toHaveBeenCalledWith('/api/users/9/otp-exempt', { otp_exempt: false })
  })
})
