import {
  CUSTOMER_KNOWLEDGE_STATUS_VALUES,
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
    throw new CustomerKnowledgeStatusAdapterError(
      `资料状态接口缺少有效字段 ${key}`
    )
  }
  return value.trim()
}

const statusValue = (value: string): CustomerKnowledgeStatusValue => {
  if (!CUSTOMER_KNOWLEDGE_STATUS_VALUES.includes(value as CustomerKnowledgeStatusValue)) {
    throw new CustomerKnowledgeStatusAdapterError('资料状态接口返回了未冻结的状态值')
  }
  return value as CustomerKnowledgeStatusValue
}

const isoTimestamp = (value: string): string => {
  if (Number.isNaN(Date.parse(value))) {
    throw new CustomerKnowledgeStatusAdapterError('资料状态接口返回了无效的检查时间')
  }
  return value
}

export const adaptCustomerKnowledgeStatus = (payload: unknown): CustomerKnowledgeStatus => {
  if (!isRecord(payload)) {
    throw new CustomerKnowledgeStatusAdapterError('资料状态接口返回了无法识别的数据格式')
  }

  return {
    status: statusValue(requiredString(payload, 'status')),
    summary: requiredString(payload, 'summary'),
    lastCheckedAt: isoTimestamp(requiredString(payload, 'last_checked_at'))
  }
}
