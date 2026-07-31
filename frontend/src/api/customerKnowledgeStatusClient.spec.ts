import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpGet = vi.hoisted(() => vi.fn())
const httpCreate = vi.hoisted(() => vi.fn(() => ({ get: httpGet })))

vi.mock('axios', () => ({
  default: {
    create: httpCreate,
    isCancel: () => false,
    isAxiosError: () => false
  }
}))

import { customerKnowledgeStatusClient } from './customerKnowledgeStatusClient'

const responsePayload = () => ({
  schema_version: 'customer-product-ai-knowledge-status.v1',
  product_id: 'PROD/001',
  status: 'PUBLISHED',
  embedding_status: 'COMPLETE',
  publication_receipt_id: 'PUB-001',
  active_collection: 'test_knowledge_v031',
  chunk_count: 3,
  embedding_count: 3,
  indexed_fingerprint: 'a'.repeat(64),
  published_at: '2026-07-31T10:00:00Z',
  last_checked_at: '2026-07-31T10:00:00Z'
})

describe('customerKnowledgeStatusClient customer-product-ai-knowledge-status.v1', () => {
  beforeEach(() => {
    httpGet.mockReset()
    httpGet.mockResolvedValue({ data: responsePayload() })
  })

  it('uses the same-origin platform proxy unless direct debug mode is configured', () => {
    expect(httpCreate).toHaveBeenCalledWith(expect.objectContaining({
      baseURL: '/platform-api'
    }))
  })

  it('calls the C-owned product publication status path', async () => {
    await customerKnowledgeStatusClient.getStatus({
      storeCode: 'PDD-SM',
      productId: 'PROD/001',
      skuId: 'SKU-RED'
    })

    expect(httpGet).toHaveBeenCalledWith(
      '/api/v1/customer-service/catalog/products/PROD%2F001/ai-knowledge',
      { signal: undefined }
    )
  })

  it('maps a malformed response to the customer-safe failure', async () => {
    httpGet.mockResolvedValueOnce({
      data: { ...responsePayload(), status: 'NOT_FROZEN' }
    })

    await expect(customerKnowledgeStatusClient.getStatus({
      storeCode: 'PDD-SM',
      productId: 'PROD/001',
      skuId: null
    })).rejects.toThrow('无法获取 AI 知识状态，可继续咨询。')
  })
})
