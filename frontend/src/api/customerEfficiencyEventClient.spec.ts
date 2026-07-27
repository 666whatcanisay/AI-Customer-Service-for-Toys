import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpPost = vi.hoisted(() => vi.fn())
const httpCreate = vi.hoisted(() => vi.fn(() => ({ post: httpPost })))

vi.mock('axios', () => ({
  default: { create: httpCreate, isCancel: () => false, isAxiosError: () => false }
}))

import {
  createCustomerEfficiencyOpaqueId,
  customerEfficiencyEventClient
} from './customerEfficiencyEventClient'

const draft = {
  eventType: 'AI_DIRECT_ADOPT' as const,
  operatorId: 'op-test-001',
  storeCode: 'PDD-SM',
  productId: 'PROD-001',
  skuId: 'SKU-RED',
  conversationId: 'conv-test-001',
  interactionId: 'int-test-001',
  feedbackId: null
}

describe('customerEfficiencyEventClient', () => {
  beforeEach(() => httpPost.mockReset())

  it('posts the frozen event endpoint with an Idempotency-Key', async () => {
    httpPost.mockResolvedValue({
      data: {
        event_id: 'CEE-001',
        event_type: 'AI_DIRECT_ADOPT',
        created_at: '2026-07-27T09:00:00Z',
        accepted: true
      }
    })

    await expect(customerEfficiencyEventClient.submit(draft, 'cee-key-001')).resolves.toEqual({
      eventId: 'CEE-001',
      eventType: 'AI_DIRECT_ADOPT',
      createdAt: '2026-07-27T09:00:00Z',
      accepted: true
    })
    expect(httpPost).toHaveBeenCalledWith('/api/v1/customer-efficiency/events', {
      schema_version: 'customer-efficiency.v1',
      event_type: 'AI_DIRECT_ADOPT',
      operator_id: 'op-test-001',
      store_code: 'PDD-SM',
      product_id: 'PROD-001',
      sku_id: 'SKU-RED',
      conversation_id: 'conv-test-001',
      interaction_id: 'int-test-001',
      feedback_id: null
    }, { headers: { 'Idempotency-Key': 'cee-key-001' } })
  })

  it('rejects a missing idempotency key or malformed receipt instead of treating it as accepted', async () => {
    httpPost.mockResolvedValue({ data: { event_id: 'CEE-001', accepted: true } })
    await expect(customerEfficiencyEventClient.submit(draft, 'cee-key-invalid')).rejects.toBeInstanceOf(Error)
    await expect(customerEfficiencyEventClient.submit(draft, '   ')).rejects.toBeInstanceOf(Error)
    expect(httpPost).toHaveBeenCalledTimes(1)
  })

  it('creates opaque IDs without using customer or employee identity fields', () => {
    expect(createCustomerEfficiencyOpaqueId('op')).toMatch(/^op-/)
    expect(createCustomerEfficiencyOpaqueId('conv')).toMatch(/^conv-/)
    expect(createCustomerEfficiencyOpaqueId('int')).toMatch(/^int-/)
    expect(createCustomerEfficiencyOpaqueId('cee')).toMatch(/^cee-/)
  })
})
