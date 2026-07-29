import { PlatformAdapterError } from './platformAdapter'
import type {
  AiInteractionEventDraft,
  AiInteractionEventReceipt
} from './aiInteractionEventTypes'

const ACTION_TYPES = ['DIRECT_ACCEPT', 'EDITED_ACCEPT', 'REJECTED'] as const
const emailPattern = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi
const phonePattern = /(?:\+?86[- ]?)?1[3-9]\d{9}/g
const identityPattern = /\d{6}(?:19|20)\d{2}[01]\d[0-3]\d{4}[\dXx]/g
const longNumberPattern = /\d{8,}/g

const isRecord = (value: unknown): value is Record<string, unknown> =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const requiredText = (value: string, field: string): string => {
  const trimmed = value.trim()
  if (!trimmed) throw new PlatformAdapterError(`AI 行为事件缺少 ${field}`)
  return trimmed
}

const optionalText = (value: string | null): string | null => value?.trim() || null

export const minimizeInteractionSummary = (value: string): string =>
  value
    .replace(emailPattern, '[邮箱已移除]')
    .replace(phonePattern, '[手机号已移除]')
    .replace(identityPattern, '[身份证号已移除]')
    .replace(longNumberPattern, '[长编号已移除]')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 240)

export const toAiInteractionEventPayload = (draft: AiInteractionEventDraft) => {
  if (!ACTION_TYPES.includes(draft.actionType)) {
    throw new PlatformAdapterError('AI 行为事件包含未知 action_type')
  }
  const finalAnswerSummary = optionalText(draft.finalAnswerSummary)
  if (draft.actionType === 'EDITED_ACCEPT' && !finalAnswerSummary) {
    throw new PlatformAdapterError('修改后采用必须包含 final_answer_summary')
  }
  const questionSummary = minimizeInteractionSummary(
    requiredText(draft.questionSummary, 'question_summary')
  )
  const aiAnswerSummary = minimizeInteractionSummary(
    requiredText(draft.aiAnswerSummary, 'ai_answer_summary')
  )
  if (!questionSummary || !aiAnswerSummary) {
    throw new PlatformAdapterError('AI 行为事件摘要不能为空')
  }

  return {
    interaction_id: requiredText(draft.interactionId, 'interaction_id'),
    store_code: requiredText(draft.storeCode, 'store_code'),
    store_name: requiredText(draft.storeName, 'store_name'),
    product_id: requiredText(draft.productId, 'product_id'),
    product_name: requiredText(draft.productName, 'product_name'),
    sku_id: optionalText(draft.skuId),
    sku_name: optionalText(draft.skuName),
    action_type: draft.actionType,
    question_summary: questionSummary,
    ai_answer_summary: aiAnswerSummary,
    final_answer_summary: finalAnswerSummary
      ? minimizeInteractionSummary(finalAnswerSummary)
      : null,
    created_by: requiredText(draft.createdBy, 'created_by')
  }
}

export const adaptAiInteractionEventReceipt = (
  value: unknown
): AiInteractionEventReceipt => {
  if (!isRecord(value)) throw new PlatformAdapterError('AI 行为事件回执格式无效')
  if (
    typeof value.event_id !== 'string' ||
    !value.event_id.trim() ||
    typeof value.interaction_id !== 'string' ||
    !value.interaction_id.trim() ||
    value.status !== 'RECORDED' ||
    typeof value.occurred_at !== 'string' ||
    Number.isNaN(Date.parse(value.occurred_at))
  ) {
    throw new PlatformAdapterError(
      'AI 行为事件回执必须包含 event_id、interaction_id、RECORDED 和 occurred_at'
    )
  }
  return {
    eventId: value.event_id.trim(),
    interactionId: value.interaction_id.trim(),
    status: 'RECORDED',
    occurredAt: value.occurred_at
  }
}
