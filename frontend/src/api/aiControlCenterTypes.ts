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
  getControlCenter(signal?: AbortSignal): Promise<AiControlCenterSnapshot>
  listModules(signal?: AbortSignal): Promise<AiModuleSummary[]>
  getModule(moduleId: string, signal?: AbortSignal): Promise<AiCapabilityDetail>
  getPrompt(moduleId: string, signal?: AbortSignal): Promise<AiPromptMetadata>
  getLatestEvaluation(moduleId: string, signal?: AbortSignal): Promise<AiLatestEvaluation>
}

export type AiControlCenterStatus =
  | 'RUNNING'
  | 'PAUSED'
  | 'ERROR'
  | 'PLANNED'
  | 'CONFIGURED'
  | 'NOT_CONFIGURED'
  | 'AVAILABLE'
  | 'NOT_AVAILABLE'
  | 'MANUAL_ONLY'

export interface AiControlCustomerServiceState {
  moduleId: 'ai_customer_service'
  name: string
  description: string
  status: 'RUNNING' | 'PAUSED' | 'ERROR'
  ready: boolean
  modelProvider: string | null
  modelName: string | null
  modelConfigured: boolean | null
  knowledgeCount: number | null
  metricsScope: string | null
  callCount: number | null
  successCount: number | null
  errorCount: number | null
  averageLatencyMs: number | null
  lastCalledAt: string | null
  lastErrorSummary: string | null
  supportedActions: string[]
}

export interface AiControlPromptState {
  moduleId: 'ai_customer_service'
  promptVersion: string
  promptHash: string
  updatedAt: string
  sourceType: string
  safePreview: string
  answerStyleRules: string[]
}

export interface AiControlEvaluationState {
  moduleId: 'ai_customer_service'
  status: 'AVAILABLE' | 'NOT_AVAILABLE'
  evaluation: AiEvaluation | null
  executionMode: 'EXPLICIT_MANUAL'
  platformIntegrationStatus: 'CONFIGURED' | 'NOT_CONFIGURED'
  currentModelVersion: string | null
  currentPromptVersion: string
  versionNote: string
}

export interface AiBadcaseCategoryState {
  category: 'FACT_ERROR' | 'MISSING_INFO' | 'STYLE_ISSUE' | 'RISK_ISSUE'
  count: null
}

export interface AiBadcaseReadOnlyState {
  status: 'NOT_AVAILABLE'
  reason: string
  categories: AiBadcaseCategoryState[]
  rawContentExposed: false
}

export interface AiFeedbackAnalysisRunSummary {
  completedAt: string
  inputFeedbackCount: number
  completedAnalysisCount: number
  analyzedWritebackCount: number
  idempotencyVerifiedCount: number
  modelVersion: string | null
  promptVersion: string | null
}

export interface AiFeedbackAnalysisReadOnlyState {
  status: 'MANUAL_ONLY' | 'NOT_CONFIGURED'
  executionMode: 'EXPLICIT_LOOPBACK'
  platformIntegrationStatus: 'CONFIGURED' | 'NOT_CONFIGURED'
  configuredModelVersion: string | null
  promptVersion: string
  latestRun: AiFeedbackAnalysisRunSummary | null
  resultRetention: 'PROCESS_MEMORY_ONLY'
  rawContentExposed: false
}

export interface AiOperationalCapability {
  capabilityId: 'rag' | 'qwen_local_model' | 'experience_evaluation' | 'badcase_analysis' | 'feedback_analysis'
  name: string
  status: AiControlCenterStatus
  dataStatus: 'AVAILABLE' | 'NOT_AVAILABLE'
  operatorMode: 'READ_ONLY' | 'EXPLICIT_MANUAL'
  summary: string
}

export interface AiControlCenterDataSource {
  sourceId: string
  readPath: string
  purpose: string
  containsRawCustomerContent: false
}

export interface AiControlCenterSnapshot {
  schemaVersion: 'ai-control-center.v1.1'
  generatedAt: string
  customerService: AiControlCustomerServiceState
  prompt: AiControlPromptState
  evaluation: AiControlEvaluationState
  badcase: AiBadcaseReadOnlyState
  feedbackAnalysis: AiFeedbackAnalysisReadOnlyState
  capabilities: AiOperationalCapability[]
  dataSources: AiControlCenterDataSource[]
}
