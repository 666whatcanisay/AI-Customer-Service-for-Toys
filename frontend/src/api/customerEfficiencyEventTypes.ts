export const CUSTOMER_EFFICIENCY_EVENT_TYPES = [
  'AI_REQUEST',
  'AI_DIRECT_ADOPT',
  'AI_EDIT_ADOPT',
  'AI_REJECT',
  'EXPERIENCE_CASE_SAVE',
  'AI_FEEDBACK_SUBMIT'
] as const

export type CustomerEfficiencyEventType = (typeof CUSTOMER_EFFICIENCY_EVENT_TYPES)[number]

export interface CustomerEfficiencyEventDraft {
  eventType: CustomerEfficiencyEventType
  operatorId: string
  storeCode: string
  productId: string | null
  skuId: string | null
  conversationId: string
  interactionId: string | null
  feedbackId: string | null
}

export interface CustomerEfficiencyEventReceipt {
  eventId: string
  eventType: CustomerEfficiencyEventType
  createdAt: string
  accepted: true
}

export interface CustomerEfficiencyEventApiClient {
  submit(
    draft: CustomerEfficiencyEventDraft,
    idempotencyKey: string
  ): Promise<CustomerEfficiencyEventReceipt>
}
