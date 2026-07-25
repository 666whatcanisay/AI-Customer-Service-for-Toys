import { PlatformAdapterError } from './platformAdapter'
import {
  EXPERIENCE_CASE_FEEDBACK_TYPES,
  EXPERIENCE_CASE_STATUSES,
  type ExperienceCaseDraft,
  type ExperienceCaseFeedbackType,
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

const isFeedbackType = (value: unknown): value is ExperienceCaseFeedbackType =>
  typeof value === 'string' && EXPERIENCE_CASE_FEEDBACK_TYPES.includes(value as ExperienceCaseFeedbackType)

const requiredFeedbackType = (value: unknown): ExperienceCaseFeedbackType => {
  if (!isFeedbackType(value)) {
    throw new PlatformAdapterError('优秀案例请求包含未冻结的 feedback_type')
  }
  return value
}

export const toExperienceCasePayload = (draft: ExperienceCaseDraft): ExperienceCaseRequestPayload => ({
  store_code: requiredText(draft.storeCode, 'store_code'),
  product_id: requiredText(draft.productId, 'product_id'),
  sku_id: draft.skuId?.trim() || null,
  question: requiredText(draft.question, 'question'),
  ai_answer: requiredText(draft.aiAnswer, 'ai_answer'),
  final_answer: requiredText(draft.finalAnswer, 'final_answer'),
  feedback_type: requiredFeedbackType(draft.feedbackType),
  created_by: requiredText(draft.createdBy, 'created_by')
})

export const adaptExperienceCaseReceipt = (payload: unknown): ExperienceCaseReceipt => {
  if (!isRecord(payload)) throw new PlatformAdapterError('优秀案例提交接口返回格式无效')
  if (typeof payload.case_id !== 'string' || !payload.case_id.trim() || !isStatus(payload.review_status)) {
    throw new PlatformAdapterError('优秀案例提交结果必须包含冻结字段 case_id 和 review_status')
  }
  return { caseId: payload.case_id.trim(), reviewStatus: payload.review_status }
}
