import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpPost = vi.hoisted(() => vi.fn())
const httpCreate = vi.hoisted(() => vi.fn(() => ({ post: httpPost })))

vi.mock('axios', () => ({
  default: { create: httpCreate, isCancel: () => false, isAxiosError: () => false }
}))

import { experienceCaseClient } from './experienceCaseClient'

const draft = {
  storeCode: 'PDD-SM', productId: 'PROD-1', skuId: 'SKU-1', question: '测试问题', aiAnswer: 'AI 测试回复',
  finalAnswer: '客服测试回复', feedbackType: 'DIRECT_ACCEPT' as const, createdBy: 'TESTER-ONE'
}

describe('experienceCaseClient', () => {
  beforeEach(() => httpPost.mockReset())

  it('posts only to the provisional C endpoint and has no Mock fallback', async () => {
    httpPost.mockResolvedValue({ data: { status: 'NEW' } })
    await expect(experienceCaseClient.submit(draft)).resolves.toEqual({ status: 'NEW' })
    expect(httpPost).toHaveBeenCalledWith('/api/v1/customer-experience-cases', {
      store_code: 'PDD-SM', product_id: 'PROD-1', sku_id: 'SKU-1', question: '测试问题', ai_answer: 'AI 测试回复',
      final_answer: '客服测试回复', feedback_type: 'DIRECT_ACCEPT', created_by: 'TESTER-ONE'
    }, { signal: undefined })
  })

  it('rejects an unrecognized C response instead of returning a local success', async () => {
    httpPost.mockResolvedValue({ data: { status: 'UNKNOWN_STATUS' } })
    let received: unknown
    try {
      await experienceCaseClient.submit(draft)
    } catch (error) {
      received = error
    }
    expect(received).toBeInstanceOf(Error)
  })
})
