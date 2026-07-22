export const RAG_ACTIONS = [
  'DIRECT_ANSWER',
  'CONTROLLED_ANSWER',
  'ASK_CLARIFY',
  'REQUIRE_LOOKUP',
  'TRANSFER_HUMAN',
  'REFUSE'
] as const

export const RISK_LEVELS = ['LOW', 'MEDIUM', 'HIGH'] as const

export type RagAction = (typeof RAG_ACTIONS)[number]
export type RiskLevel = (typeof RISK_LEVELS)[number]
export type AdoptionType = 'DIRECT_ACCEPT' | 'EDITED_ACCEPT' | 'REJECTED'

export interface RagHealth {
  status: string
  ready: boolean
}

export interface RagChatRequest {
  message: string
}

export interface RagCitation {
  file: string
  page: number | null
  chunkId: string | null
  summary: string
  distance: number | null
  knowledgeVersion: string | null
}

export interface RagChatResult {
  requestId: string | null
  model: string | null
  answer: string
  action: RagAction | null
  riskLevel: RiskLevel | null
  citations: RagCitation[]
  warnings: string[]
  requiredFields: string[]
  latencyMs: number | null
}

export interface AdoptionRecord {
  requestId: string | null
  type: AdoptionType
  originalAnswer: string
  finalAnswer: string
}

export interface RagApiClient {
  getHealth(signal?: AbortSignal): Promise<RagHealth>
  chat(request: RagChatRequest, signal?: AbortSignal): Promise<RagChatResult>
}
