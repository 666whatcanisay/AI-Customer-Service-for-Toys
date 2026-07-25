import { PlatformAdapterError } from './platformAdapter'
import {
  EXPERIENCE_CASE_STATUSES,
  type ExperienceCaseDraft,
  type ExperienceCaseReceipt,
  type ExperienceCaseStatus
} from './experienceCaseTypes'

type UnknownRecord = Record<string, unknown>

export interface ExperienceCaseRequestPayload {
  store_code: string
  product_id: string
  sku_id: string | null
  question: string
  ai_answer: string
  final_answer: string
  feedback_type: ExperienceCaseDraft['feedbackType']
  created_by: string
}

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const requiredText = (value: string, key: string): string => {
  const trimmed = value.trim()
  if (!trimmed) throw new PlatformAdapterError(`优秀案例请求缺少非空字段 ${key}`)
  return trimmed
}

const isStatus = (value: unknown): value is ExperienceCaseStatus =>
  typeof value === 'string' && EXPERIENCE_CASE_STATUSES.includes(value as ExperienceCaseStatus)

export const toExperienceCasePayload = (draft: ExperienceCaseDraft): ExperienceCaseRequestPayload => ({
  store_code: requiredText(draft.storeCode, 'store_code'),
  product_id: requiredText(draft.productId, 'product_id'),
  sku_id: draft.skuId?.trim() || null,
  question: requiredText(draft.question, 'question'),
  ai_answer: requiredText(draft.aiAnswer, 'ai_answer'),
  final_answer: draft.finalAnswer.trim(),
  feedback_type: draft.feedbackType,
  created_by: requiredText(draft.createdBy, 'created_by')
})

export const adaptExperienceCaseReceipt = (payload: unknown): ExperienceCaseReceipt => {
  if (!isRecord(payload)) throw new PlatformAdapterError('优秀案例提交接口返回格式无效')
  const record = 'data' in payload ? payload.data : payload
  if (!isRecord(record) || !isStatus(record.status)) {
    throw new PlatformAdapterError('优秀案例提交结果缺少冻结状态字段 status')
  }
  return { status: record.status }
}
