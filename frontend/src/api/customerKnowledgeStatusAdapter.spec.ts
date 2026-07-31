import { describe, expect, it } from 'vitest'
import {
  adaptCustomerKnowledgeStatus,
  CustomerKnowledgeStatusAdapterError
} from './customerKnowledgeStatusAdapter'

const publishedPayload = () => ({
  schema_version: 'customer-product-ai-knowledge-status.v1',
  product_id: 'PROD-001',
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

describe('customerKnowledgeStatusAdapter customer-product-ai-knowledge-status.v1', () => {
  it('adapts only the frozen C-owned publication evidence', () => {
    expect(adaptCustomerKnowledgeStatus({
      ...publishedPayload(),
      raw_document: 'must never be rendered by the customer client'
    })).toEqual({
      productId: 'PROD-001',
      status: 'PUBLISHED',
      embeddingStatus: 'COMPLETE',
      publicationReceiptId: 'PUB-001',
      activeCollection: 'test_knowledge_v031',
      chunkCount: 3,
      embeddingCount: 3,
      indexedFingerprint: 'a'.repeat(64),
      publishedAt: '2026-07-31T10:00:00Z',
      lastCheckedAt: '2026-07-31T10:00:00Z'
    })
  })

  it('rejects incompatible schemas, unknown statuses, and malformed evidence', () => {
    expect(() => adaptCustomerKnowledgeStatus({
      ...publishedPayload(),
      schema_version: 'legacy-status.v1'
    })).toThrow(CustomerKnowledgeStatusAdapterError)
    expect(() => adaptCustomerKnowledgeStatus({
      ...publishedPayload(),
      status: 'READY'
    })).toThrow(CustomerKnowledgeStatusAdapterError)
    expect(() => adaptCustomerKnowledgeStatus({
      ...publishedPayload(),
      chunk_count: -1
    })).toThrow(CustomerKnowledgeStatusAdapterError)
  })
})
