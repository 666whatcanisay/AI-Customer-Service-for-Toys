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
  getOperationsOverview(signal?: AbortSignal): Promise<AiOperationsOverviewSnapshot>
  getQualityBaseline(signal?: AbortSignal): Promise<AiQualityBaselineSnapshot>
  listModules(signal?: AbortSignal): Promise<AiModuleSummary[]>
  getModule(moduleId: string, signal?: AbortSignal): Promise<AiCapabilityDetail>
  getPrompt(moduleId: string, signal?: AbortSignal): Promise<AiPromptMetadata>
  getLatestEvaluation(moduleId: string, signal?: AbortSignal): Promise<AiLatestEvaluation>
}

export type AiMetricStatus = 'AVAILABLE' | 'NOT_AVAILABLE'
export type AiExternalDataStatus = AiMetricStatus | 'NOT_CONFIGURED' | 'NOT_REGISTERED'
export type AiNoticeSeverity = 'INFO' | 'WARNING' | 'ERROR'
export type AiBadcaseCategory = 'FACT_ERROR' | 'MISSING_INFO' | 'STYLE_ISSUE' | 'RISK_ISSUE'
export type AiQualityDiagnosisCategory =
  | 'KNOWLEDGE_PROBLEM'
  | 'RETRIEVAL_PROBLEM'
  | 'PROMPT_OR_MODEL_PROBLEM'
  | 'DATA_PROBLEM'
  | 'RULE_DECISION_PROBLEM'

export interface AiAnswerVolumeMetric {
  status: AiMetricStatus
  metricsScope: string
  processedRequestCount: number | null
  directAnswerCount: number | null
  controlledAnswerCount: number | null
  transferHumanCount: number | null
  otherOutcomeCount: number | null
  durable: false
  explanation: string
}

export interface AiAnswerQualityMetric {
  status: AiMetricStatus
  evaluationId: string | null
  evaluatedCaseCount: number | null
  passedCaseCount: number | null
  passRatePercent: number | null
  measuredAt: string | null
  explanation: string
}

export interface AiKnowledgeCoverageMetric {
  status: AiMetricStatus
  indexedChunkCount: number | null
  sourceAttributionCheckedCaseCount: number | null
  sourceAttributionPassRatePercent: number | null
  explanation: string
}

export interface AiOperationsBadcaseMetric {
  status: 'NOT_AVAILABLE'
  categories: Array<{ category: AiBadcaseCategory; count: null }>
  explanation: string
  rawContentExposed: false
}

export interface AiModelStatusMetric {
  status: 'CONFIGURED' | 'NOT_CONFIGURED'
  provider: string | null
  modelVersion: string | null
  serviceReady: boolean
  availabilityProbed: false
  averageLatencyMs: number | null
  errorCount: number | null
  lastErrorCategory: string | null
  explanation: string
}

export interface AiExternalDataMetric {
  sourceId: 'feedback' | 'efficiency'
  status: AiExternalDataStatus
  readAttempted: false
  explanation: string
  operatorAction: string
}

export interface AiOperationsNotice {
  code: string
  severity: AiNoticeSeverity
  message: string
  operatorAction: string
  automaticActionTaken: false
}

export interface AiOperationsOverviewSnapshot {
  schemaVersion: 'ai-operations.v1'
  generatedAt: string
  answerVolume: AiAnswerVolumeMetric
  answerQuality: AiAnswerQualityMetric
  knowledgeCoverage: AiKnowledgeCoverageMetric
  badcase: AiOperationsBadcaseMetric
  modelStatus: AiModelStatusMetric
  externalData: AiExternalDataMetric[]
  notices: AiOperationsNotice[]
  rawContentExposed: false
}

export interface AiQualityCheckSummary {
  check: 'action' | 'source_ids' | 'key_facts' | 'forbidden_claims' | 'required_fields' | 'risk_level' | 'scope'
  passedCaseCount: number | null
}

export interface AiQualityBaselineSummary {
  evaluationId: string
  executedAt: string
  datasetVersion: string
  totalCaseCount: number
  passedCaseCount: number
  failedCaseCount: number
  passRatePercent: number
  checks: AiQualityCheckSummary[]
}

export interface AiFailedCaseDiagnosis {
  caseId: string
  categories: AiQualityDiagnosisCategory[]
  evaluatorFailureClasses: Array<'metadata_loss' | 'retrieval_miss' | 'model_expression_error' | 'structured_decision_error'>
  failedChecks: Array<'action' | 'source_ids' | 'key_facts' | 'forbidden_claims' | 'required_fields' | 'risk_level' | 'scope'>
  expectedSourceCount: number
  missingExpectedSourceCount: number
  expectedFactCount: number
  suggestedVerifications: string[]
}

export interface AiQualityCauseFinding {
  category: AiQualityDiagnosisCategory
  affectedCaseCount: number
  evidence: 'DIRECT_EVALUATOR_SIGNAL' | 'NO_SIGNAL_IN_CURRENT_REPORT'
  conclusion: string
  recommendedVerification: string
  automaticChangeAllowed: false
}

export interface AiQualityRecommendation {
  priority: 'P0' | 'P1' | 'P2'
  category: AiQualityDiagnosisCategory
  recommendation: string
  rationale: string
  automaticChangeAllowed: false
}

export interface AiQualityBaselineSnapshot {
  schemaVersion: 'ai-quality-baseline.v1'
  status: AiMetricStatus
  summary: AiQualityBaselineSummary | null
  failedCases: AiFailedCaseDiagnosis[]
  causeFindings: AiQualityCauseFinding[]
  recommendations: AiQualityRecommendation[]
  rawContentExposed: false
  modelOrPromptChanged: false
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
