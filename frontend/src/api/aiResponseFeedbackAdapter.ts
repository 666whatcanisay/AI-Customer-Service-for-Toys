import { PlatformAdapterError } from './platformAdapter'
import {
  AI_RESPONSE_FEEDBACK_STATUSES,
  AI_RESPONSE_FEEDBACK_TYPES,
  type AiResponseFeedbackDraft,
  type AiResponseFeedbackReceipt,
  type AiResponseFeedbackStatus,
  type AiResponseFeedbackType
} from './aiResponseFeedbackTypes'

type UnknownRecord = Record<string, unknown>

export interface AiResponseFeedbackRequestPayload {
  store_code: string
  product_id: string | null
  sku_id: string | null
  question: string
  ai_answer: string
  feedback_type: AiResponseFeedbackType
  feedback_note: string | null
  final_answer: string | null
  created_by: string
  context: {
    store_code: string
    product_id: string | null
    sku_id: string | null
  }
}

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const requiredText = (value: string, key: string): string => {
  const trimmed = value.trim()
  if (!trimmed) throw new PlatformAdapterError(`AI 问题反馈请求缺少非空字段 ${key}`)
  return trimmed
}

const optionalText = (value: string | null): string | null => value?.trim() || null

const isFeedbackType = (value: unknown): value is AiResponseFeedbackType =>
  typeof value === 'string' && AI_RESPONSE_FEEDBACK_TYPES.includes(value as AiResponseFeedbackType)

const isStatus = (value: unknown): value is AiResponseFeedbackStatus =>
  typeof value === 'string' && AI_RESPONSE_FEEDBACK_STATUSES.includes(value as AiResponseFeedbackStatus)

const requiredFeedbackType = (value: unknown): AiResponseFeedbackType => {
  if (!isFeedbackType(value)) {
    throw new PlatformAdapterError('AI 问题反馈请求包含未冻结的 feedback_type')
  }
  return value
}

export const toAiResponseFeedbackPayload = (
  draft: AiResponseFeedbackDraft
): AiResponseFeedbackRequestPayload => {
  const storeCode = requiredText(draft.storeCode, 'store_code')
  const productId = optionalText(draft.productId)
  const skuId = optionalText(draft.skuId)
  const feedbackType = requiredFeedbackType(draft.feedbackType)
  const feedbackNote = optionalText(draft.feedbackNote)

  if (feedbackType === 'OTHER' && !feedbackNote) {
    throw new PlatformAdapterError('选择“其他”时必须填写 feedback_note')
  }

  return {
    store_code: storeCode,
    product_id: productId,
    sku_id: skuId,
    question: requiredText(draft.question, 'question'),
    ai_answer: requiredText(draft.aiAnswer, 'ai_answer'),
    feedback_type: feedbackType,
    feedback_note: feedbackNote,
    final_answer: optionalText(draft.finalAnswer),
    created_by: requiredText(draft.createdBy, 'created_by'),
    context: {
      store_code: storeCode,
      product_id: productId,
      sku_id: skuId
    }
  }
}

export const adaptAiResponseFeedbackReceipt = (payload: unknown): AiResponseFeedbackReceipt => {
  if (!isRecord(payload)) throw new PlatformAdapterError('AI 问题反馈提交接口返回格式无效')
  if (
    typeof payload.feedback_id !== 'string' ||
    !payload.feedback_id.trim() ||
    payload.status !== 'NEW' ||
    !isStatus(payload.status)
  ) {
    throw new PlatformAdapterError(
      'AI 问题反馈提交结果必须包含冻结字段 feedback_id 和 NEW 状态'
    )
  }
  return {
    feedbackId: payload.feedback_id.trim(),
    status: payload.status
  }
}
