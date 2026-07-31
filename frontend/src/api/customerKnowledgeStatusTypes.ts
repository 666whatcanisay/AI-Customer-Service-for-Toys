export const CUSTOMER_KNOWLEDGE_STATUS_VALUES = [
  'NOT_GENERATED',
  'GENERATING',
  'PUBLISHED',
  'SYNC_FAILED',
  'NEED_RESYNC'
] as const

export const CUSTOMER_EMBEDDING_STATUS_VALUES = [
  'NOT_GENERATED',
  'GENERATING',
  'COMPLETE',
  'FAILED'
] as const

export type CustomerKnowledgeStatusValue =
  (typeof CUSTOMER_KNOWLEDGE_STATUS_VALUES)[number]

export type CustomerEmbeddingStatusValue =
  (typeof CUSTOMER_EMBEDDING_STATUS_VALUES)[number]

export interface CustomerKnowledgeStatusScope {
  storeCode: string
  productId: string
  skuId: string | null
}

export interface CustomerKnowledgeStatus {
  productId: string
  status: CustomerKnowledgeStatusValue
  embeddingStatus: CustomerEmbeddingStatusValue
  publicationReceiptId: string | null
  activeCollection: string | null
  chunkCount: number
  embeddingCount: number
  indexedFingerprint: string | null
  publishedAt: string | null
  lastCheckedAt: string
}

export interface CustomerKnowledgeStatusClient {
  getStatus(
    scope: CustomerKnowledgeStatusScope,
    signal?: AbortSignal
  ): Promise<CustomerKnowledgeStatus>
}
