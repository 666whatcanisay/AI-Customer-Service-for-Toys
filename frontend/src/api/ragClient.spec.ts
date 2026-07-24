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

describe('ragClient proxy base URL', () => {
  it('uses the same-origin RAG proxy by default', () => {
    expect(httpCreate).toHaveBeenCalledWith(expect.objectContaining({
      baseURL: '/rag-api'
    }))
    expect(ragClient).toBeDefined()
  })
})
