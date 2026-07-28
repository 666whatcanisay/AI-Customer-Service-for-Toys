import { beforeEach, describe, expect, it, vi } from 'vitest'

const aiGet = vi.hoisted(() => vi.fn())

vi.mock('axios', () => {
  class AxiosError extends Error {}

  return {
    default: {
      create: vi.fn((config: { baseURL?: string }) => ({
        get: config.baseURL === '/ai-api' ? aiGet : vi.fn(),
      })),
    },
    AxiosError,
  }
})

import { listAiModules } from '../src/api/client'

describe('listAiModules', () => {
  beforeEach(() => aiGet.mockReset())

  it('unwraps the frozen A success envelope from data.modules', async () => {
    aiGet.mockResolvedValue({
      data: {
        success: true,
        message: 'ok',
        data: {
          modules: [{
            module_id: 'ai_customer_service',
            name: 'AI Customer Service',
            description: 'Provides controlled customer-service answers.',
            status: 'RUNNING',
          }],
        },
      },
    })

    await expect(listAiModules()).resolves.toEqual([{
      id: 'ai_customer_service',
      name: 'AI Customer Service',
      status: 'RUNNING',
      description: 'Provides controlled customer-service answers.',
      implemented: false,
      promptMetadata: null,
      recentEvaluations: [],
    }])
    expect(aiGet).toHaveBeenCalledWith('/api/admin/ai/modules')
  })

  it('does not reinterpret malformed, legacy, or non-success shapes as modules', async () => {
    aiGet.mockResolvedValue({ data: { success: true, data: { items: [{ module_id: 'wrong-shape' }] } } })
    await expect(listAiModules()).rejects.toThrow('模块列表')

    aiGet.mockResolvedValue({ data: [{ module_id: 'legacy-array' }] })
    await expect(listAiModules()).rejects.toThrow('未返回成功')

    aiGet.mockResolvedValue({ data: { success: false, data: { modules: [{ module_id: 'not-successful' }] } } })
    await expect(listAiModules()).rejects.toThrow('未返回成功')
  })
})
