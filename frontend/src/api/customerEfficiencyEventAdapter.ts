import { PlatformAdapterError } from './platformAdapter'
import {
  CUSTOMER_EFFICIENCY_EVENT_TYPES,
  type CustomerEfficiencyEventDraft,
  type CustomerEfficiencyEventReceipt,
  type CustomerEfficiencyEventType
} from './customerEfficiencyEventTypes'

type UnknownRecord = Record<string, unknown>

export interface CustomerEfficiencyEventRequestPayload {
  schema_version: 'customer-efficiency.v1'
  event_type: CustomerEfficiencyEventType
  operator_id: string
  store_code: string
  product_id: string | null
  sku_id: string | null
  conversation_id: string
  interaction_id: string | null
  feedback_id: string | null
}

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const isEventType = (value: unknown): value is CustomerEfficiencyEventType =>
  typeof value === 'string' && CUSTOMER_EFFICIENCY_EVENT_TYPES.includes(value as CustomerEfficiencyEventType)

const requiredText = (value: string, key: string): string => {
  const normalized = value.trim()
  if (!normalized) throw new PlatformAdapterError(`客服效率事件缺少非空字段 ${key}`)
  return normalized
}

const optionalText = (value: string | null): string | null => value?.trim() || null

const requiresInteraction = (eventType: CustomerEfficiencyEventType): boolean =>
  eventType === 'AI_REQUEST' ||
  eventType === 'AI_DIRECT_ADOPT' ||
  eventType === 'AI_EDIT_ADOPT' ||
  eventType === 'AI_REJECT'

const isRfc3339 = (value: string): boolean =>
  /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})$/.test(value) &&
  !Number.isNaN(Date.parse(value))

export const toCustomerEfficiencyEventPayload = (
  draft: CustomerEfficiencyEventDraft
): CustomerEfficiencyEventRequestPayload => {
  if (!isEventType(draft.eventType)) {
    throw new PlatformAdapterError('客服效率事件包含未冻结的 event_type')
  }

  const interactionId = optionalText(draft.interactionId)
  const feedbackId = optionalText(draft.feedbackId)
  if (requiresInteraction(draft.eventType) && !interactionId) {
    throw new PlatformAdapterError('该客服效率事件必须关联 interaction_id')
  }
  if (draft.eventType !== 'AI_FEEDBACK_SUBMIT' && feedbackId) {
    throw new PlatformAdapterError('Non-feedback efficiency events must not include feedback_id')
  }
  if (draft.eventType === 'AI_FEEDBACK_SUBMIT' && !feedbackId) {
    throw new PlatformAdapterError('AI_FEEDBACK_SUBMIT 必须关联 feedback_id')
  }

  return {
    schema_version: 'customer-efficiency.v1',
    event_type: draft.eventType,
    operator_id: requiredText(draft.operatorId, 'operator_id'),
    store_code: requiredText(draft.storeCode, 'store_code'),
    product_id: optionalText(draft.productId),
    sku_id: optionalText(draft.skuId),
    conversation_id: requiredText(draft.conversationId, 'conversation_id'),
    interaction_id: interactionId,
    feedback_id: feedbackId
  }
}

export const adaptCustomerEfficiencyEventReceipt = (
  payload: unknown,
  expectedEventType: CustomerEfficiencyEventType
): CustomerEfficiencyEventReceipt => {
  if (!isRecord(payload)) throw new PlatformAdapterError('客服效率事件接口返回格式无效')
  if (
    typeof payload.event_id !== 'string' ||
    !payload.event_id.trim() ||
    payload.event_type !== expectedEventType ||
    !isEventType(payload.event_type) ||
    payload.accepted !== true ||
    typeof payload.created_at !== 'string' ||
    !isRfc3339(payload.created_at)
  ) {
    throw new PlatformAdapterError('客服效率事件提交结果不符合冻结回执')
  }

  return {
    eventId: payload.event_id.trim(),
    eventType: payload.event_type,
    createdAt: payload.created_at,
    accepted: true
  }
}
