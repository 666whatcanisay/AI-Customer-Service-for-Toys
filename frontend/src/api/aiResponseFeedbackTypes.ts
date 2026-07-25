export const AI_RESPONSE_FEEDBACK_TYPES = [
  'FACT_ERROR',
  'MISSING_INFO',
  'STYLE_ISSUE',
  'RISK_ISSUE',
  'OTHER'
] as const

export const AI_RESPONSE_FEEDBACK_STATUSES = ['NEW', 'ANALYZING', 'ANALYZED'] as const

export type AiResponseFeedbackType = (typeof AI_RESPONSE_FEEDBACK_TYPES)[number]
export type AiResponseFeedbackStatus = (typeof AI_RESPONSE_FEEDBACK_STATUSES)[number]

export interface AiResponseFeedbackDraft {
  storeCode: string
  productId: string | null
  skuId: string | null
  question: string
  aiAnswer: string
  feedbackType: AiResponseFeedbackType
  feedbackNote: string | null
  finalAnswer: string | null
  createdBy: string
}

export interface AiResponseFeedbackReceipt {
  feedbackId: string
  status: AiResponseFeedbackStatus
  analysisStatus: AiResponseFeedbackStatus
  createdAt: string
}

export interface AiResponseFeedbackApiClient {
  submit(draft: AiResponseFeedbackDraft, signal?: AbortSignal): Promise<AiResponseFeedbackReceipt>
}
