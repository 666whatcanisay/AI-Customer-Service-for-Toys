export const SUGGESTION_CATEGORIES = [
  'BUG',
  'IMPROVEMENT',
  'NEW_FEATURE',
  'DATA_ISSUE',
  'OTHER'
] as const

export const SUGGESTION_FREQUENCIES = ['ONCE', 'OCCASIONAL', 'FREQUENT', 'DAILY'] as const

export const SUGGESTION_URGENCIES = ['LOW', 'MEDIUM', 'HIGH'] as const

export type SuggestionCategory = (typeof SUGGESTION_CATEGORIES)[number]
export type SuggestionFrequency = (typeof SUGGESTION_FREQUENCIES)[number]
export type SuggestionUrgency = (typeof SUGGESTION_URGENCIES)[number]

export interface SuggestionDraft {
  reporterId: string
  reporterName: string
  storeCode: string | null
  moduleKey: string
  category: SuggestionCategory
  title: string
  description: string
  frequency: SuggestionFrequency
  urgency: SuggestionUrgency
}

export interface SuggestionReceipt {
  suggestionId: string
  status: string
}

export interface SuggestionSummary {
  suggestionId: string
  reporterId: string
  storeCode: string | null
  moduleKey: string
  category: SuggestionCategory
  title: string
  frequency: SuggestionFrequency
  urgency: SuggestionUrgency
  status: string
}

export interface SuggestionList {
  items: SuggestionSummary[]
  total: number
}

export interface SuggestionApiClient {
  submit(draft: SuggestionDraft, signal?: AbortSignal): Promise<SuggestionReceipt>
  listMine(reporterId: string, signal?: AbortSignal): Promise<SuggestionList>
}
