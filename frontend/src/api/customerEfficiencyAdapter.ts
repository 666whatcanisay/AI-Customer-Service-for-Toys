import {
  CUSTOMER_EFFICIENCY_EVENT_TYPES,
  type CustomerEfficiencyEventDraft,
  type CustomerEfficiencyEventReceipt,
  type CustomerEfficiencyEventType,
} from './customerEfficiencyTypes'

type UnknownRecord = Record<string, unknown>

export class CustomerEfficiencyAdapterError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'CustomerEfficiencyAdapterError'
  }
}

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const requiredText = (value: string | null, field: string): string => {
  const normalized = value?.trim() ?? ''
  if (!normalized) throw new CustomerEfficiencyAdapterError(`效率事件缺少 ${field}`)
  return normalized
}

const optionalText = (value: string | null): string | null => value?.trim() || null

export const toCustomerEfficiencyPayload = (draft: CustomerEfficiencyEventDraft) => {
  const eventType = draft.eventType
  const interactionId = optionalText(draft.interactionId)
  if ((eventType === 'AI_REQUEST' || eventType === 'AI_DIRECT_ADOPT' || eventType === 'AI_EDIT_ADOPT' || eventType === 'AI_REJECT') && !interactionId) {
    throw new CustomerEfficiencyAdapterError('AI 请求和采用结果必须关联本次 AI 交互。')
  }
  const feedbackId = optionalText(draft.feedbackId)
  if (eventType === 'AI_FEEDBACK_SUBMIT' && !feedbackId) {
    throw new CustomerEfficiencyAdapterError('AI 问题反馈事件缺少反馈回执。')
  }
  return {
    schema_version: 'customer-efficiency.v1',
    event_type: eventType,
    operator_id: requiredText(draft.operatorId, '客服身份'),
    store_code: requiredText(draft.storeCode, '店铺'),
    product_id: optionalText(draft.productId),
    sku_id: optionalText(draft.skuId),
    conversation_id: optionalText(draft.conversationId),
    interaction_id: interactionId,
    feedback_id: feedbackId,
  }
}

export const adaptCustomerEfficiencyReceipt = (payload: unknown): CustomerEfficiencyEventReceipt => {
  if (!isRecord(payload) || payload.accepted !== true || typeof payload.event_id !== 'string' || !payload.event_id.trim()) {
    throw new CustomerEfficiencyAdapterError('C 效率事件接口未返回可用回执。')
  }
  if (typeof payload.event_type !== 'string' || !CUSTOMER_EFFICIENCY_EVENT_TYPES.includes(payload.event_type as CustomerEfficiencyEventType)) {
    throw new CustomerEfficiencyAdapterError('C 效率事件回执包含未知事件类型。')
  }
  if (typeof payload.created_at !== 'string' || !payload.created_at.trim()) {
    throw new CustomerEfficiencyAdapterError('C 效率事件回执缺少创建时间。')
  }
  return {
    eventId: payload.event_id.trim(),
    eventType: payload.event_type as CustomerEfficiencyEventType,
    accepted: true,
    createdAt: payload.created_at,
  }
}
