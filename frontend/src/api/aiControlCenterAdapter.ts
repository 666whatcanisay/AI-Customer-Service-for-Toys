import { RagAdapterError } from './ragAdapter'
import {
  AI_MODULE_STATUSES,
  type AiCapabilityDetail,
  type AiBadcaseCategoryState,
  type AiControlCenterDataSource,
  type AiControlCenterSnapshot,
  type AiControlCenterStatus,
  type AiControlCustomerServiceState,
  type AiControlEvaluationState,
  type AiControlPromptState,
  type AiEvaluation,
  type AiFeedbackAnalysisReadOnlyState,
  type AiFeedbackAnalysisRunSummary,
  type AiLatestEvaluation,
  type AiModuleStatus,
  type AiModuleSummary,
  type AiOperationalCapability,
  type AiPromptMetadata
} from './aiControlCenterTypes'

type UnknownRecord = Record<string, unknown>

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const unwrapData = (payload: unknown): UnknownRecord => {
  if (!isRecord(payload) || !isRecord(payload.data)) {
    throw new RagAdapterError('AI 控制中心只接受包含 data 的 A API 响应')
  }
  return payload.data
}

const nullableText = (value: unknown, field: string): string | null => {
  if (value === null || value === undefined) return null
  if (typeof value !== 'string') throw new RagAdapterError(`AI 控制中心字段 ${field} 必须为 string 或 null`)
  const trimmed = value.trim()
  return trimmed && trimmed !== 'NOT_AVAILABLE' ? trimmed : null
}

const nullableNumber = (value: unknown, field: string): number | null => {
  if (value === null || value === undefined) return null
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new RagAdapterError(`AI 控制中心字段 ${field} 必须为有限数字或 null`)
  }
  return value
}

const requiredNumber = (value: unknown, field: string): number => {
  const result = nullableNumber(value, field)
  if (result === null) throw new RagAdapterError(`AI 控制中心响应缺少 ${field}`)
  return result
}

const nullableBoolean = (value: unknown, field: string): boolean | null => {
  if (value === null || value === undefined) return null
  if (typeof value !== 'boolean') throw new RagAdapterError(`AI 控制中心字段 ${field} 必须为 boolean 或 null`)
  return value
}

const requiredText = (value: unknown, field: string): string => {
  const result = nullableText(value, field)
  if (!result) throw new RagAdapterError(`AI 控制中心响应缺少 ${field}`)
  return result
}

const moduleStatus = (value: unknown): AiModuleStatus => {
  if (typeof value !== 'string' || !AI_MODULE_STATUSES.includes(value as AiModuleStatus)) {
    throw new RagAdapterError('AI 控制中心模块状态不在已发布枚举内')
  }
  return value as AiModuleStatus
}

const requiredStringList = (value: unknown, field: string): string[] => {
  if (!Array.isArray(value) || !value.every((item) => typeof item === 'string')) {
    throw new RagAdapterError(`AI 控制中心字段 ${field} 必须为 string[]`)
  }
  return value.map((item) => item.trim()).filter(Boolean)
}

const requiredBoolean = (value: unknown, field: string): boolean => {
  if (typeof value !== 'boolean') throw new RagAdapterError(`AI 控制中心字段 ${field} 必须为 boolean`)
  return value
}

const stringLiteral = <T extends string>(value: unknown, values: readonly T[], field: string): T => {
  if (typeof value !== 'string' || !values.includes(value as T)) {
    throw new RagAdapterError(`AI 控制中心字段 ${field} 不在已发布枚举内`)
  }
  return value as T
}

const adaptModuleSummary = (value: unknown): AiModuleSummary => {
  if (!isRecord(value)) throw new RagAdapterError('AI 控制中心模块记录格式无效')
  if (typeof value.implemented !== 'boolean') {
    throw new RagAdapterError('AI 控制中心模块字段 implemented 必须为 boolean')
  }
  return {
    moduleId: requiredText(value.module_id, 'module_id'),
    name: requiredText(value.name, 'name'),
    description: requiredText(value.description, 'description'),
    status: moduleStatus(value.status),
    implemented: value.implemented
  }
}

export const adaptAiModulesResponse = (payload: unknown): AiModuleSummary[] => {
  const data = unwrapData(payload)
  if (!Array.isArray(data.modules)) throw new RagAdapterError('AI 控制中心响应缺少 modules 数组')
  return data.modules.map(adaptModuleSummary)
}

export const adaptAiModuleDetailResponse = (payload: unknown): AiCapabilityDetail => {
  const data = unwrapData(payload)
  const summary = adaptModuleSummary(data)
  return {
    ...summary,
    modelProvider: nullableText(data.model_provider, 'model_provider'),
    modelName: nullableText(data.model_name, 'model_name'),
    ready: nullableBoolean(data.ready, 'ready'),
    modelConfigured: nullableBoolean(data.model_configured, 'model_configured'),
    initializationError: nullableText(data.initialization_error, 'initialization_error'),
    knowledgeCount: nullableNumber(data.knowledge_count, 'knowledge_count'),
    promptVersion: nullableText(data.prompt_version, 'prompt_version'),
    promptHash: nullableText(data.prompt_hash, 'prompt_hash'),
    metricsScope: nullableText(data.metrics_scope, 'metrics_scope'),
    callCount: nullableNumber(data.call_count, 'call_count'),
    successCount: nullableNumber(data.success_count, 'success_count'),
    errorCount: nullableNumber(data.error_count, 'error_count'),
    averageLatencyMs: nullableNumber(data.average_latency_ms, 'average_latency_ms'),
    lastCalledAt: nullableText(data.last_called_at, 'last_called_at')
  }
}

export const adaptAiPromptResponse = (payload: unknown): AiPromptMetadata => {
  const data = unwrapData(payload)
  return {
    moduleId: requiredText(data.module_id, 'module_id'),
    status: nullableText(data.status, 'status'),
    promptVersion: nullableText(data.prompt_version, 'prompt_version'),
    promptHash: nullableText(data.prompt_hash, 'prompt_hash'),
    updatedAt: nullableText(data.updated_at, 'updated_at'),
    sourceType: nullableText(data.source_type, 'source_type'),
    safePreview: nullableText(data.safe_preview, 'safe_preview'),
    answerStyleRules: data.answer_style_rules === undefined
      ? []
      : requiredStringList(data.answer_style_rules, 'answer_style_rules')
  }
}

const adaptEvaluation = (value: unknown): AiEvaluation | null => {
  if (value === null || value === undefined) return null
  if (!isRecord(value)) throw new RagAdapterError('AI 控制中心 evaluation 格式无效')
  const checkSource = value.checks
  if (!isRecord(checkSource)) throw new RagAdapterError('AI 控制中心 evaluation.checks 格式无效')
  const checks: Record<string, number | null> = {}
  for (const key of ['action', 'source_ids', 'key_facts', 'required_fields', 'risk_level', 'scope']) {
    checks[key] = nullableNumber(checkSource[key], `checks.${key}`)
  }
  if (typeof value.report_available !== 'boolean') {
    throw new RagAdapterError('AI 控制中心字段 evaluation.report_available 必须为 boolean')
  }
  return {
    evaluationId: nullableText(value.evaluation_id, 'evaluation_id'),
    executedAt: nullableText(value.executed_at, 'executed_at'),
    datasetVersion: nullableText(value.dataset_version, 'dataset_version'),
    totalCases: nullableNumber(value.total_cases, 'total_cases'),
    passedCases: nullableNumber(value.passed_cases, 'passed_cases'),
    passRate: nullableNumber(value.pass_rate, 'pass_rate'),
    checks,
    failedCaseIds: requiredStringList(value.failed_case_ids, 'failed_case_ids'),
    reportAvailable: value.report_available
  }
}

export const adaptAiLatestEvaluationResponse = (payload: unknown): AiLatestEvaluation => {
  const data = unwrapData(payload)
  if (data.status !== 'AVAILABLE' && data.status !== 'NOT_AVAILABLE') {
    throw new RagAdapterError('AI 控制中心评测状态不在已发布枚举内')
  }
  return {
    moduleId: requiredText(data.module_id, 'module_id'),
    status: data.status,
    evaluation: adaptEvaluation(data.evaluation)
  }
}

const CONTROL_CENTER_STATUSES = [
  'RUNNING', 'PAUSED', 'ERROR', 'PLANNED', 'CONFIGURED', 'NOT_CONFIGURED',
  'AVAILABLE', 'NOT_AVAILABLE', 'MANUAL_ONLY'
] as const

const adaptControlEvaluation = (value: unknown): AiEvaluation | null => {
  if (value === null) return null
  if (!isRecord(value)) throw new RagAdapterError('AI 控制中心评测摘要格式无效')
  const checkSource = value.checks
  if (!isRecord(checkSource)) throw new RagAdapterError('AI 控制中心评测检查项格式无效')
  const checks: Record<string, number | null> = {}
  for (const key of ['action', 'source_ids', 'key_facts', 'required_fields', 'risk_level', 'scope']) {
    checks[key] = nullableNumber(checkSource[key], `evaluation.checks.${key}`)
  }
  return {
    evaluationId: requiredText(value.evaluation_id, 'evaluation.evaluation_id'),
    executedAt: requiredText(value.executed_at, 'evaluation.executed_at'),
    datasetVersion: requiredText(value.dataset_version, 'evaluation.dataset_version'),
    totalCases: nullableNumber(value.total_cases, 'evaluation.total_cases'),
    passedCases: nullableNumber(value.passed_cases, 'evaluation.passed_cases'),
    passRate: nullableNumber(value.pass_rate, 'evaluation.pass_rate'),
    checks,
    failedCaseIds: requiredStringList(value.failed_case_ids, 'evaluation.failed_case_ids'),
    reportAvailable: requiredBoolean(value.report_available, 'evaluation.report_available')
  }
}

const adaptControlCustomerService = (value: unknown): AiControlCustomerServiceState => {
  if (!isRecord(value)) throw new RagAdapterError('AI 控制中心客户服务状态格式无效')
  const moduleId = stringLiteral(value.module_id, ['ai_customer_service'] as const, 'customer_service.module_id')
  return {
    moduleId,
    name: requiredText(value.name, 'customer_service.name'),
    description: requiredText(value.description, 'customer_service.description'),
    status: stringLiteral(value.status, ['RUNNING', 'PAUSED', 'ERROR'] as const, 'customer_service.status'),
    ready: requiredBoolean(value.ready, 'customer_service.ready'),
    modelProvider: nullableText(value.model_provider, 'customer_service.model_provider'),
    modelName: nullableText(value.model_name, 'customer_service.model_name'),
    modelConfigured: nullableBoolean(value.model_configured, 'customer_service.model_configured'),
    knowledgeCount: nullableNumber(value.knowledge_count, 'customer_service.knowledge_count'),
    metricsScope: nullableText(value.metrics_scope, 'customer_service.metrics_scope'),
    callCount: nullableNumber(value.call_count, 'customer_service.call_count'),
    successCount: nullableNumber(value.success_count, 'customer_service.success_count'),
    errorCount: nullableNumber(value.error_count, 'customer_service.error_count'),
    averageLatencyMs: nullableNumber(value.average_latency_ms, 'customer_service.average_latency_ms'),
    lastCalledAt: nullableText(value.last_called_at, 'customer_service.last_called_at'),
    lastErrorSummary: nullableText(value.last_error_summary, 'customer_service.last_error_summary'),
    supportedActions: requiredStringList(value.supported_actions, 'customer_service.supported_actions')
  }
}

const adaptControlPrompt = (value: unknown): AiControlPromptState => {
  if (!isRecord(value)) throw new RagAdapterError('AI 控制中心 Prompt 状态格式无效')
  return {
    moduleId: stringLiteral(value.module_id, ['ai_customer_service'] as const, 'prompt.module_id'),
    promptVersion: requiredText(value.prompt_version, 'prompt.prompt_version'),
    promptHash: requiredText(value.prompt_hash, 'prompt.prompt_hash'),
    updatedAt: requiredText(value.updated_at, 'prompt.updated_at'),
    sourceType: requiredText(value.source_type, 'prompt.source_type'),
    safePreview: requiredText(value.safe_preview, 'prompt.safe_preview'),
    answerStyleRules: requiredStringList(value.answer_style_rules, 'prompt.answer_style_rules')
  }
}

const adaptControlEvaluationState = (value: unknown): AiControlEvaluationState => {
  if (!isRecord(value)) throw new RagAdapterError('AI 控制中心评测状态格式无效')
  return {
    moduleId: stringLiteral(value.module_id, ['ai_customer_service'] as const, 'evaluation.module_id'),
    status: stringLiteral(value.status, ['AVAILABLE', 'NOT_AVAILABLE'] as const, 'evaluation.status'),
    evaluation: adaptControlEvaluation(value.evaluation),
    executionMode: stringLiteral(value.execution_mode, ['EXPLICIT_MANUAL'] as const, 'evaluation.execution_mode'),
    platformIntegrationStatus: stringLiteral(value.platform_integration_status, ['CONFIGURED', 'NOT_CONFIGURED'] as const, 'evaluation.platform_integration_status'),
    currentModelVersion: nullableText(value.current_model_version, 'evaluation.current_model_version'),
    currentPromptVersion: requiredText(value.current_prompt_version, 'evaluation.current_prompt_version'),
    versionNote: requiredText(value.version_note, 'evaluation.version_note')
  }
}

const adaptBadcaseCategories = (value: unknown): AiBadcaseCategoryState[] => {
  if (!Array.isArray(value)) throw new RagAdapterError('AI 控制中心 Badcase 分类必须为数组')
  return value.map((item, index) => {
    if (!isRecord(item) || item.count !== null) {
      throw new RagAdapterError(`AI 控制中心 Badcase 分类 ${index} 格式无效`)
    }
    return {
      category: stringLiteral(item.category, ['FACT_ERROR', 'MISSING_INFO', 'STYLE_ISSUE', 'RISK_ISSUE'] as const, `badcase.categories.${index}.category`),
      count: null
    }
  })
}

const adaptFeedbackRun = (value: unknown): AiFeedbackAnalysisRunSummary | null => {
  if (value === null) return null
  if (!isRecord(value)) throw new RagAdapterError('AI 控制中心反馈分析摘要格式无效')
  return {
    completedAt: requiredText(value.completed_at, 'feedback_analysis.latest_run.completed_at'),
    inputFeedbackCount: requiredNumber(value.input_feedback_count, 'feedback_analysis.latest_run.input_feedback_count'),
    completedAnalysisCount: requiredNumber(value.completed_analysis_count, 'feedback_analysis.latest_run.completed_analysis_count'),
    analyzedWritebackCount: requiredNumber(value.analyzed_writeback_count, 'feedback_analysis.latest_run.analyzed_writeback_count'),
    idempotencyVerifiedCount: requiredNumber(value.idempotency_verified_count, 'feedback_analysis.latest_run.idempotency_verified_count'),
    modelVersion: nullableText(value.model_version, 'feedback_analysis.latest_run.model_version'),
    promptVersion: nullableText(value.prompt_version, 'feedback_analysis.latest_run.prompt_version')
  }
}

const adaptCapabilities = (value: unknown): AiOperationalCapability[] => {
  if (!Array.isArray(value)) throw new RagAdapterError('AI 控制中心能力清单必须为数组')
  return value.map((item, index) => {
    if (!isRecord(item)) throw new RagAdapterError(`AI 控制中心能力 ${index} 格式无效`)
    return {
      capabilityId: stringLiteral(item.capability_id, ['rag', 'qwen_local_model', 'experience_evaluation', 'badcase_analysis', 'feedback_analysis'] as const, `capabilities.${index}.capability_id`),
      name: requiredText(item.name, `capabilities.${index}.name`),
      status: stringLiteral(item.status, CONTROL_CENTER_STATUSES, `capabilities.${index}.status`) as AiControlCenterStatus,
      dataStatus: stringLiteral(item.data_status, ['AVAILABLE', 'NOT_AVAILABLE'] as const, `capabilities.${index}.data_status`),
      operatorMode: stringLiteral(item.operator_mode, ['READ_ONLY', 'EXPLICIT_MANUAL'] as const, `capabilities.${index}.operator_mode`),
      summary: requiredText(item.summary, `capabilities.${index}.summary`)
    }
  })
}

const adaptDataSources = (value: unknown): AiControlCenterDataSource[] => {
  if (!Array.isArray(value)) throw new RagAdapterError('AI 控制中心数据来源必须为数组')
  return value.map((item, index) => {
    if (!isRecord(item)) throw new RagAdapterError(`AI 控制中心数据来源 ${index} 格式无效`)
    if (item.contains_raw_customer_content !== false) {
      throw new RagAdapterError('AI 控制中心数据来源不能包含原始客户内容')
    }
    return {
      sourceId: requiredText(item.source_id, `data_sources.${index}.source_id`),
      readPath: requiredText(item.read_path, `data_sources.${index}.read_path`),
      purpose: requiredText(item.purpose, `data_sources.${index}.purpose`),
      containsRawCustomerContent: false
    }
  })
}

export const adaptAiControlCenterResponse = (payload: unknown): AiControlCenterSnapshot => {
  const data = unwrapData(payload)
  if (data.schema_version !== 'ai-control-center.v1.1') {
    throw new RagAdapterError('AI 控制中心快照版本不受支持')
  }
  if (!isRecord(data.badcase) || !isRecord(data.feedback_analysis)) {
    throw new RagAdapterError('AI 控制中心缺少 Badcase 或反馈分析状态')
  }
  if (data.badcase.status !== 'NOT_AVAILABLE' || data.badcase.raw_content_exposed !== false) {
    throw new RagAdapterError('AI 控制中心 Badcase 安全状态无效')
  }
  const feedbackAnalysis: AiFeedbackAnalysisReadOnlyState = {
    status: stringLiteral(data.feedback_analysis.status, ['MANUAL_ONLY', 'NOT_CONFIGURED'] as const, 'feedback_analysis.status'),
    executionMode: stringLiteral(data.feedback_analysis.execution_mode, ['EXPLICIT_LOOPBACK'] as const, 'feedback_analysis.execution_mode'),
    platformIntegrationStatus: stringLiteral(data.feedback_analysis.platform_integration_status, ['CONFIGURED', 'NOT_CONFIGURED'] as const, 'feedback_analysis.platform_integration_status'),
    configuredModelVersion: nullableText(data.feedback_analysis.configured_model_version, 'feedback_analysis.configured_model_version'),
    promptVersion: requiredText(data.feedback_analysis.prompt_version, 'feedback_analysis.prompt_version'),
    latestRun: adaptFeedbackRun(data.feedback_analysis.latest_run),
    resultRetention: stringLiteral(data.feedback_analysis.result_retention, ['PROCESS_MEMORY_ONLY'] as const, 'feedback_analysis.result_retention'),
    rawContentExposed: false
  }
  return {
    schemaVersion: 'ai-control-center.v1.1',
    generatedAt: requiredText(data.generated_at, 'generated_at'),
    customerService: adaptControlCustomerService(data.customer_service),
    prompt: adaptControlPrompt(data.prompt),
    evaluation: adaptControlEvaluationState(data.evaluation),
    badcase: {
      status: 'NOT_AVAILABLE',
      reason: requiredText(data.badcase.reason, 'badcase.reason'),
      categories: adaptBadcaseCategories(data.badcase.categories),
      rawContentExposed: false
    },
    feedbackAnalysis,
    capabilities: adaptCapabilities(data.capabilities),
    dataSources: adaptDataSources(data.data_sources)
  }
}
