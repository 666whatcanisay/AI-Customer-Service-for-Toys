import { describe, expect, it, vi } from 'vitest'

const httpCreate = vi.hoisted(() => vi.fn(() => ({ get: vi.fn(), post: vi.fn() })))

vi.mock('axios', () => ({
  default: {
    create: httpCreate,
    isCancel: () => false,
    isAxiosError: () => false
  }
}))

import { ragClient } from './ragClient'

describe('ragClient authenticated workspace base URL', () => {
  it('uses the same-origin Platform proxy so direct A chat is not browser-exposed', () => {
    expect(httpCreate).toHaveBeenCalledWith(expect.objectContaining({
      baseURL: '/platform-api'
    }))
    expect(ragClient).toBeDefined()
  })
})
