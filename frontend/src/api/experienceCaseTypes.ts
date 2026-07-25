import type { AdoptionType } from './ragTypes'

export const EXPERIENCE_CASE_STATUSES = ['NEW', 'REVIEWING', 'APPROVED', 'REJECTED'] as const

export type ExperienceCaseStatus = (typeof EXPERIENCE_CASE_STATUSES)[number]

export interface ExperienceCaseDraft {
  storeCode: string
  productId: string
  skuId: string | null
  question: string
  aiAnswer: string
  finalAnswer: string
  feedbackType: AdoptionType
  createdBy: string
}

export interface ExperienceCaseReceipt {
  status: ExperienceCaseStatus
}

export interface ExperienceCaseSubmission {
  storeCode: string
  productId: string
  skuId: string | null
  feedbackType: AdoptionType
  createdBy: string
  status: ExperienceCaseStatus
  submittedAt: string
}

export interface ExperienceCaseApiClient {
  submit(draft: ExperienceCaseDraft, signal?: AbortSignal): Promise<ExperienceCaseReceipt>
}
