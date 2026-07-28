import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpPost = vi.hoisted(() => vi.fn())
const httpCreate = vi.hoisted(() => vi.fn(() => ({ post: httpPost })))

vi.mock('axios', () => ({
  default: { create: httpCreate, isAxiosError: () => false }
}))

import { customerEfficiencyClient } from './customerEfficiencyClient'

const draft = {
  eventType: 'AI_REQUEST' as const,
  operatorId: 'CSU-001',
  storeCode: 'PDD-SM',
  productId: 'PROD-001',
  skuId: 'SKU-001',
  conversationId: null,
  interactionId: 'interaction-001',
  feedbackId: null
}

describe('customerEfficiencyClient', () => {
  beforeEach(() => httpPost.mockReset())

  it('posts only a v1 behavior event to C with the caller idempotency key', async () => {
    httpPost.mockResolvedValue({ data: { event_id: 'CEE-001', event_type: 'AI_REQUEST', accepted: true, created_at: '2026-07-28T00:00:00Z' } })

    await expect(customerEfficiencyClient.submit(draft, 'customer-efficiency-replay-001')).resolves.toMatchObject({
      eventId: 'CEE-001', eventType: 'AI_REQUEST', accepted: true
    })
    expect(httpPost).toHaveBeenCalledWith('/api/v1/customer-efficiency/events', {
      schema_version: 'customer-efficiency.v1', event_type: 'AI_REQUEST', operator_id: 'CSU-001',
      store_code: 'PDD-SM', product_id: 'PROD-001', sku_id: 'SKU-001', conversation_id: null,
      interaction_id: 'interaction-001', feedback_id: null
    }, { signal: undefined, headers: { 'Idempotency-Key': 'customer-efficiency-replay-001' } })
  })
})
