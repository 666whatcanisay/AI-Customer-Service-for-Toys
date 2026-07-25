export const EXPERIENCE_CASE_STATUSES = ['NEW', 'REVIEWING', 'APPROVED', 'REJECTED'] as const
export const EXPERIENCE_CASE_FEEDBACK_TYPES = [
  'ADOPTED',
  'EDITED_ADOPTED',
  'CORRECTION',
  'ESCALATED'
] as const

export type ExperienceCaseStatus = (typeof EXPERIENCE_CASE_STATUSES)[number]
export type ExperienceCaseFeedbackType = (typeof EXPERIENCE_CASE_FEEDBACK_TYPES)[number]

export interface ExperienceCaseDraft {
  storeCode: string
  productId: string
  skuId: string | null
  question: string
  aiAnswer: string
  finalAnswer: string
  feedbackType: ExperienceCaseFeedbackType
  createdBy: string
}

export interface ExperienceCaseReceipt {
  caseId: string
  reviewStatus: ExperienceCaseStatus
}

export interface ExperienceCaseSubmission {
  caseId: string
  storeCode: string
  productId: string
  skuId: string | null
  feedbackType: ExperienceCaseFeedbackType
  createdBy: string
  reviewStatus: ExperienceCaseStatus
  submittedAt: string
}

export interface ExperienceCaseApiClient {
  submit(draft: ExperienceCaseDraft, signal?: AbortSignal): Promise<ExperienceCaseReceipt>
}
