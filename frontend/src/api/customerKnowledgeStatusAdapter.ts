import {
  CUSTOMER_EMBEDDING_STATUS_VALUES,
  CUSTOMER_KNOWLEDGE_STATUS_VALUES,
  type CustomerEmbeddingStatusValue,
  type CustomerKnowledgeStatus,
  type CustomerKnowledgeStatusValue
} from './customerKnowledgeStatusTypes'

type UnknownRecord = Record<string, unknown>

export class CustomerKnowledgeStatusAdapterError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'CustomerKnowledgeStatusAdapterError'
  }
}

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const requiredString = (record: UnknownRecord, key: string): string => {
  const value = record[key]
  if (typeof value !== 'string' || !value.trim()) {
    throw new CustomerKnowledgeStatusAdapterError(`AI 知识状态接口缺少有效字段 ${key}`)
  }
  return value.trim()
}

const nullableString = (record: UnknownRecord, key: string): string | null => {
  const value = record[key]
  if (value === null) return null
  if (typeof value !== 'string' || !value.trim()) {
    throw new CustomerKnowledgeStatusAdapterError(`AI 知识状态接口字段 ${key} 无效`)
  }
  return value.trim()
}

const nonNegativeInteger = (record: UnknownRecord, key: string): number => {
  const value = record[key]
  if (!Number.isInteger(value) || (value as number) < 0) {
    throw new CustomerKnowledgeStatusAdapterError(`AI 知识状态接口字段 ${key} 无效`)
  }
  return value as number
}

const knowledgeStatus = (value: string): CustomerKnowledgeStatusValue => {
  if (!CUSTOMER_KNOWLEDGE_STATUS_VALUES.includes(value as CustomerKnowledgeStatusValue)) {
    throw new CustomerKnowledgeStatusAdapterError('AI 知识状态接口返回了未冻结的状态值')
  }
  return value as CustomerKnowledgeStatusValue
}

const embeddingStatus = (value: string): CustomerEmbeddingStatusValue => {
  if (!CUSTOMER_EMBEDDING_STATUS_VALUES.includes(value as CustomerEmbeddingStatusValue)) {
    throw new CustomerKnowledgeStatusAdapterError('AI 知识状态接口返回了未冻结的向量状态值')
  }
  return value as CustomerEmbeddingStatusValue
}

const isoTimestamp = (value: string): string => {
  if (Number.isNaN(Date.parse(value))) {
    throw new CustomerKnowledgeStatusAdapterError('AI 知识状态接口返回了无效时间')
  }
  return value
}

const nullableIsoTimestamp = (record: UnknownRecord, key: string): string | null => {
  const value = nullableString(record, key)
  return value === null ? null : isoTimestamp(value)
}

export const adaptCustomerKnowledgeStatus = (payload: unknown): CustomerKnowledgeStatus => {
  if (!isRecord(payload)) {
    throw new CustomerKnowledgeStatusAdapterError('AI 知识状态接口返回了无法识别的数据格式')
  }
  if (requiredString(payload, 'schema_version') !== 'customer-product-ai-knowledge-status.v1') {
    throw new CustomerKnowledgeStatusAdapterError('AI 知识状态接口版本不兼容')
  }

  return {
    productId: requiredString(payload, 'product_id'),
    status: knowledgeStatus(requiredString(payload, 'status')),
    embeddingStatus: embeddingStatus(requiredString(payload, 'embedding_status')),
    publicationReceiptId: nullableString(payload, 'publication_receipt_id'),
    activeCollection: nullableString(payload, 'active_collection'),
    chunkCount: nonNegativeInteger(payload, 'chunk_count'),
    embeddingCount: nonNegativeInteger(payload, 'embedding_count'),
    indexedFingerprint: nullableString(payload, 'indexed_fingerprint'),
    publishedAt: nullableIsoTimestamp(payload, 'published_at'),
    lastCheckedAt: isoTimestamp(requiredString(payload, 'last_checked_at'))
  }
}
