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

export interface RagChatContext {
  tenant_id: string
  platform: string
  store_code: string
  product_id: string
  sku_id: string | null
}

export type RagChatRequest =
  | { question: string; context: RagChatContext; resolution_id?: never }
  | { question: string; resolution_id: string; context?: never }

export interface RagCitation {
  file: string
  page: number | null
  chunkId: string | null
  summary: string
  distance: number | null
  knowledgeVersion: string | null
  sourceIds: string[]
  productId: string | null
  skuId: string | null
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
  context: RagChatContext
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
