export const AI_MODULE_STATUSES = [
  'PLANNED',
  'DEVELOPING',
  'TESTING',
  'RUNNING',
  'PAUSED',
  'ERROR'
] as const

export type AiModuleStatus = (typeof AI_MODULE_STATUSES)[number]

export interface AiModuleSummary {
  moduleId: string
  name: string
  description: string
  status: AiModuleStatus
  implemented: boolean
}

export interface AiCapabilityDetail extends AiModuleSummary {
  modelProvider: string | null
  modelName: string | null
  ready: boolean | null
  modelConfigured: boolean | null
  initializationError: string | null
  knowledgeCount: number | null
  promptVersion: string | null
  promptHash: string | null
  metricsScope: string | null
  callCount: number | null
  successCount: number | null
  errorCount: number | null
  averageLatencyMs: number | null
  lastCalledAt: string | null
}

export interface AiPromptMetadata {
  moduleId: string
  status: string | null
  promptVersion: string | null
  promptHash: string | null
  updatedAt: string | null
  sourceType: string | null
  safePreview: string | null
  answerStyleRules: string[]
}

export interface AiEvaluation {
  evaluationId: string | null
  executedAt: string | null
  datasetVersion: string | null
  totalCases: number | null
  passedCases: number | null
  passRate: number | null
  checks: Record<string, number | null>
  failedCaseIds: string[]
  reportAvailable: boolean
}

export interface AiLatestEvaluation {
  moduleId: string
  status: 'AVAILABLE' | 'NOT_AVAILABLE'
  evaluation: AiEvaluation | null
}

export interface AiControlCenterApiClient {
  listModules(signal?: AbortSignal): Promise<AiModuleSummary[]>
  getModule(moduleId: string, signal?: AbortSignal): Promise<AiCapabilityDetail>
  getPrompt(moduleId: string, signal?: AbortSignal): Promise<AiPromptMetadata>
  getLatestEvaluation(moduleId: string, signal?: AbortSignal): Promise<AiLatestEvaluation>
}
