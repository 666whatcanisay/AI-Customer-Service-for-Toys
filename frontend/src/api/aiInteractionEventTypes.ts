import type { AdoptionType } from './ragTypes'

export type AiInteractionActionType = AdoptionType
export type AiInteractionEventStatus = 'RECORDED'

export interface AiInteractionEventDraft {
  interactionId: string
  storeCode: string
  storeName: string
  productId: string
  productName: string
  skuId: string | null
  skuName: string | null
  actionType: AiInteractionActionType
  questionSummary: string
  aiAnswerSummary: string
  finalAnswerSummary: string | null
  createdBy: string
}

export interface AiInteractionEventReceipt {
  eventId: string
  interactionId: string
  status: AiInteractionEventStatus
  occurredAt: string
}

export interface AiInteractionEventApiClient {
  submit(
    draft: AiInteractionEventDraft,
    idempotencyKey: string,
    signal?: AbortSignal
  ): Promise<AiInteractionEventReceipt>
}
