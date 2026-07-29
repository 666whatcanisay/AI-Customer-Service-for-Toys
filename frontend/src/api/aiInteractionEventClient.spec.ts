import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpPost = vi.hoisted(() => vi.fn())
const httpCreate = vi.hoisted(() => vi.fn(() => ({ post: httpPost })))

vi.mock('axios', () => ({
  default: { create: httpCreate, isCancel: () => false, isAxiosError: () => false }
}))

import {
  aiInteractionEventClient,
  createAiInteractionEventIdempotencyKey
} from './aiInteractionEventClient'

const draft = {
  interactionId: 'request-001',
  storeCode: 'STORE-ONE',
  storeName: '测试店铺',
  productId: 'PRODUCT-ONE',
  productName: '测试商品',
  skuId: null,
  skuName: null,
  actionType: 'REJECTED' as const,
  questionSummary: '测试问题',
  aiAnswerSummary: '测试回复',
  finalAnswerSummary: null,
  createdBy: 'TESTER-ONE'
}

describe('aiInteractionEventClient', () => {
  beforeEach(() => httpPost.mockReset())

  it('saves the event with an explicit Idempotency-Key and consumes only RECORDED', async () => {
    httpPost.mockResolvedValue({
      data: {
        event_id: 'AIE-001',
        interaction_id: 'request-001',
        status: 'RECORDED',
        occurred_at: '2026-07-29T08:00:00Z'
      }
    })
    const key = createAiInteractionEventIdempotencyKey()
    await expect(aiInteractionEventClient.submit(draft, key)).resolves.toMatchObject({
      eventId: 'AIE-001',
      status: 'RECORDED'
    })
    expect(httpPost).toHaveBeenCalledWith(
      '/api/v1/ai-interaction-events',
      expect.objectContaining({
        interaction_id: 'request-001',
        action_type: 'REJECTED',
        store_code: 'STORE-ONE',
        product_id: 'PRODUCT-ONE'
      }),
      { signal: undefined, headers: { 'Idempotency-Key': key } }
    )
  })

  it('does not report success for a missing key or invalid receipt', async () => {
    httpPost.mockResolvedValue({
      data: {
        event_id: 'AIE-001',
        interaction_id: 'request-001',
        status: 'NEW',
        occurred_at: '2026-07-29T08:00:00Z'
      }
    })
    await expect(aiInteractionEventClient.submit(draft, '')).rejects.toBeInstanceOf(Error)
    await expect(aiInteractionEventClient.submit(draft, 'event-key')).rejects.toBeInstanceOf(Error)
  })
})
