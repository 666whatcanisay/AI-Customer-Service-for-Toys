export const CUSTOMER_KNOWLEDGE_STATUS_VALUES = [
  'READY',
  'NEEDS_REVIEW',
  'NO_APPROVED_MATERIAL',
  'UNAVAILABLE'
] as const

export type CustomerKnowledgeStatusValue =
  (typeof CUSTOMER_KNOWLEDGE_STATUS_VALUES)[number]

export interface CustomerKnowledgeStatusScope {
  storeCode: string
  productId: string
  skuId: string | null
}

export interface CustomerKnowledgeStatus {
  status: CustomerKnowledgeStatusValue
  summary: string
  lastCheckedAt: string
}

export interface CustomerKnowledgeStatusClient {
  getStatus(
    scope: CustomerKnowledgeStatusScope,
    signal?: AbortSignal
  ): Promise<CustomerKnowledgeStatus>
}
