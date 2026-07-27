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
  type AiOperationsOverviewSnapshot,
  type AiQualityBaselineSnapshot,
  type AiQualityDiagnosisCategory,
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
    executedAt: requiredLiteralText(value.executed_at, 'evaluation.executed_at'),
    datasetVersion: requiredLiteralText(value.dataset_version, 'evaluation.dataset_version'),
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

const metricStatus = (value: unknown, field: string) =>
  stringLiteral(value, ['AVAILABLE', 'NOT_AVAILABLE'] as const, field)

const qualityCategory = (value: unknown, field: string): AiQualityDiagnosisCategory =>
  stringLiteral(value, [
    'KNOWLEDGE_PROBLEM', 'RETRIEVAL_PROBLEM', 'PROMPT_OR_MODEL_PROBLEM',
    'DATA_PROBLEM', 'RULE_DECISION_PROBLEM'
  ] as const, field)

const requiredRecord = (value: unknown, field: string): UnknownRecord => {
  if (!isRecord(value)) throw new RagAdapterError(`AI 控制中心字段 ${field} 必须为对象`)
  return value
}

// Quality reports use the explicit string NOT_AVAILABLE for persisted metadata
// that was not recorded. Unlike nullable API fields, retain that provenance for
// the read-only workbench instead of silently converting it to null.
const requiredLiteralText = (value: unknown, field: string): string => {
  if (typeof value !== 'string' || !value.trim()) {
    throw new RagAdapterError(`AI 控制中心字段 ${field} 必须为非空字符串`)
  }
  return value.trim()
}

const requiredList = (value: unknown, field: string): unknown[] => {
  if (!Array.isArray(value)) throw new RagAdapterError(`AI 控制中心字段 ${field} 必须为数组`)
  return value
}

const exactFalse = (value: unknown, field: string): false => {
  if (value !== false) throw new RagAdapterError(`AI 控制中心字段 ${field} 必须为 false`)
  return false
}

const adaptOperationsBadcase = (value: unknown) => {
  const source = requiredRecord(value, 'badcase')
  if (source.status !== 'NOT_AVAILABLE') throw new RagAdapterError('AI 控制中心 Badcase 只能展示安全空态')
  return {
    status: 'NOT_AVAILABLE' as const,
    categories: requiredList(source.categories, 'badcase.categories').map((item, index) => {
      const category = requiredRecord(item, `badcase.categories.${index}`)
      if (category.count !== null) throw new RagAdapterError('AI 控制中心 Badcase 不可展示未发布的计数')
      return {
        category: stringLiteral(category.category, ['FACT_ERROR', 'MISSING_INFO', 'STYLE_ISSUE', 'RISK_ISSUE'] as const, `badcase.categories.${index}.category`),
        count: null
      }
    }),
    explanation: requiredText(source.explanation, 'badcase.explanation'),
    rawContentExposed: exactFalse(source.raw_content_exposed, 'badcase.raw_content_exposed')
  }
}

export const adaptAiOperationsOverviewResponse = (payload: unknown): AiOperationsOverviewSnapshot => {
  const data = unwrapData(payload)
  if (data.schema_version !== 'ai-operations.v1') throw new RagAdapterError('不支持的 AI 运营快照版本')
  const answerVolume = requiredRecord(data.answer_volume, 'answer_volume')
  const answerQuality = requiredRecord(data.answer_quality, 'answer_quality')
  const knowledgeCoverage = requiredRecord(data.knowledge_coverage, 'knowledge_coverage')
  const modelStatus = requiredRecord(data.model_status, 'model_status')
  return {
    schemaVersion: 'ai-operations.v1',
    generatedAt: requiredText(data.generated_at, 'generated_at'),
    answerVolume: {
      status: metricStatus(answerVolume.status, 'answer_volume.status'),
      metricsScope: requiredText(answerVolume.metrics_scope, 'answer_volume.metrics_scope'),
      processedRequestCount: nullableNumber(answerVolume.processed_request_count, 'answer_volume.processed_request_count'),
      directAnswerCount: nullableNumber(answerVolume.direct_answer_count, 'answer_volume.direct_answer_count'),
      controlledAnswerCount: nullableNumber(answerVolume.controlled_answer_count, 'answer_volume.controlled_answer_count'),
      transferHumanCount: nullableNumber(answerVolume.transfer_human_count, 'answer_volume.transfer_human_count'),
      otherOutcomeCount: nullableNumber(answerVolume.other_outcome_count, 'answer_volume.other_outcome_count'),
      durable: exactFalse(answerVolume.durable, 'answer_volume.durable'),
      explanation: requiredText(answerVolume.explanation, 'answer_volume.explanation')
    },
    answerQuality: {
      status: metricStatus(answerQuality.status, 'answer_quality.status'),
      evaluationId: nullableText(answerQuality.evaluation_id, 'answer_quality.evaluation_id'),
      evaluatedCaseCount: nullableNumber(answerQuality.evaluated_case_count, 'answer_quality.evaluated_case_count'),
      passedCaseCount: nullableNumber(answerQuality.passed_case_count, 'answer_quality.passed_case_count'),
      passRatePercent: nullableNumber(answerQuality.pass_rate_percent, 'answer_quality.pass_rate_percent'),
      measuredAt: nullableText(answerQuality.measured_at, 'answer_quality.measured_at'),
      explanation: requiredText(answerQuality.explanation, 'answer_quality.explanation')
    },
    knowledgeCoverage: {
      status: metricStatus(knowledgeCoverage.status, 'knowledge_coverage.status'),
      indexedChunkCount: nullableNumber(knowledgeCoverage.indexed_chunk_count, 'knowledge_coverage.indexed_chunk_count'),
      sourceAttributionCheckedCaseCount: nullableNumber(knowledgeCoverage.source_attribution_checked_case_count, 'knowledge_coverage.source_attribution_checked_case_count'),
      sourceAttributionPassRatePercent: nullableNumber(knowledgeCoverage.source_attribution_pass_rate_percent, 'knowledge_coverage.source_attribution_pass_rate_percent'),
      explanation: requiredText(knowledgeCoverage.explanation, 'knowledge_coverage.explanation')
    },
    badcase: adaptOperationsBadcase(data.badcase),
    modelStatus: {
      status: stringLiteral(modelStatus.status, ['CONFIGURED', 'NOT_CONFIGURED'] as const, 'model_status.status'),
      provider: nullableText(modelStatus.provider, 'model_status.provider'),
      modelVersion: nullableText(modelStatus.model_version, 'model_status.model_version'),
      serviceReady: requiredBoolean(modelStatus.service_ready, 'model_status.service_ready'),
      availabilityProbed: exactFalse(modelStatus.availability_probed, 'model_status.availability_probed'),
      averageLatencyMs: nullableNumber(modelStatus.average_latency_ms, 'model_status.average_latency_ms'),
      errorCount: nullableNumber(modelStatus.error_count, 'model_status.error_count'),
      lastErrorCategory: nullableText(modelStatus.last_error_category, 'model_status.last_error_category'),
      explanation: requiredText(modelStatus.explanation, 'model_status.explanation')
    },
    externalData: requiredList(data.external_data, 'external_data').map((item, index) => {
      const source = requiredRecord(item, `external_data.${index}`)
      return {
        sourceId: stringLiteral(source.source_id, ['feedback', 'efficiency'] as const, `external_data.${index}.source_id`),
        status: stringLiteral(source.status, ['AVAILABLE', 'NOT_AVAILABLE', 'NOT_CONFIGURED', 'NOT_REGISTERED'] as const, `external_data.${index}.status`),
        readAttempted: exactFalse(source.read_attempted, `external_data.${index}.read_attempted`),
        explanation: requiredText(source.explanation, `external_data.${index}.explanation`),
        operatorAction: requiredText(source.operator_action, `external_data.${index}.operator_action`)
      }
    }),
    notices: requiredList(data.notices, 'notices').map((item, index) => {
      const notice = requiredRecord(item, `notices.${index}`)
      return {
        code: requiredText(notice.code, `notices.${index}.code`),
        severity: stringLiteral(notice.severity, ['INFO', 'WARNING', 'ERROR'] as const, `notices.${index}.severity`),
        message: requiredText(notice.message, `notices.${index}.message`),
        operatorAction: requiredText(notice.operator_action, `notices.${index}.operator_action`),
        automaticActionTaken: exactFalse(notice.automatic_action_taken, `notices.${index}.automatic_action_taken`)
      }
    }),
    rawContentExposed: exactFalse(data.raw_content_exposed, 'raw_content_exposed')
  }
}

const adaptQualitySummary = (value: unknown) => {
  if (value === null) return null
  const summary = requiredRecord(value, 'summary')
  return {
    evaluationId: requiredText(summary.evaluation_id, 'summary.evaluation_id'),
    executedAt: requiredLiteralText(summary.executed_at, 'summary.executed_at'),
    datasetVersion: requiredLiteralText(summary.dataset_version, 'summary.dataset_version'),
    totalCaseCount: requiredNumber(summary.total_case_count, 'summary.total_case_count'),
    passedCaseCount: requiredNumber(summary.passed_case_count, 'summary.passed_case_count'),
    failedCaseCount: requiredNumber(summary.failed_case_count, 'summary.failed_case_count'),
    passRatePercent: requiredNumber(summary.pass_rate_percent, 'summary.pass_rate_percent'),
    checks: requiredList(summary.checks, 'summary.checks').map((item, index) => {
      const check = requiredRecord(item, `summary.checks.${index}`)
      return {
        check: stringLiteral(check.check, ['action', 'source_ids', 'key_facts', 'forbidden_claims', 'required_fields', 'risk_level', 'scope'] as const, `summary.checks.${index}.check`),
        passedCaseCount: nullableNumber(check.passed_case_count, `summary.checks.${index}.passed_case_count`)
      }
    })
  }
}

export const adaptAiQualityBaselineResponse = (payload: unknown): AiQualityBaselineSnapshot => {
  const data = unwrapData(payload)
  if (data.schema_version !== 'ai-quality-baseline.v1') throw new RagAdapterError('不支持的 AI 质量基线版本')
  return {
    schemaVersion: 'ai-quality-baseline.v1',
    status: metricStatus(data.status, 'status'),
    summary: adaptQualitySummary(data.summary),
    failedCases: requiredList(data.failed_cases, 'failed_cases').map((item, index) => {
      const failedCase = requiredRecord(item, `failed_cases.${index}`)
      return {
        caseId: requiredText(failedCase.case_id, `failed_cases.${index}.case_id`),
        categories: requiredList(failedCase.categories, `failed_cases.${index}.categories`).map((category, categoryIndex) => qualityCategory(category, `failed_cases.${index}.categories.${categoryIndex}`)),
        evaluatorFailureClasses: requiredList(failedCase.evaluator_failure_classes, `failed_cases.${index}.evaluator_failure_classes`).map((item, itemIndex) => stringLiteral(item, ['metadata_loss', 'retrieval_miss', 'model_expression_error', 'structured_decision_error'] as const, `failed_cases.${index}.evaluator_failure_classes.${itemIndex}`)),
        failedChecks: requiredList(failedCase.failed_checks, `failed_cases.${index}.failed_checks`).map((item, itemIndex) => stringLiteral(item, ['action', 'source_ids', 'key_facts', 'forbidden_claims', 'required_fields', 'risk_level', 'scope'] as const, `failed_cases.${index}.failed_checks.${itemIndex}`)),
        expectedSourceCount: requiredNumber(failedCase.expected_source_count, `failed_cases.${index}.expected_source_count`),
        missingExpectedSourceCount: requiredNumber(failedCase.missing_expected_source_count, `failed_cases.${index}.missing_expected_source_count`),
        expectedFactCount: requiredNumber(failedCase.expected_fact_count, `failed_cases.${index}.expected_fact_count`),
        suggestedVerifications: requiredStringList(failedCase.suggested_verifications, `failed_cases.${index}.suggested_verifications`)
      }
    }),
    causeFindings: requiredList(data.cause_findings, 'cause_findings').map((item, index) => {
      const finding = requiredRecord(item, `cause_findings.${index}`)
      return {
        category: qualityCategory(finding.category, `cause_findings.${index}.category`),
        affectedCaseCount: requiredNumber(finding.affected_case_count, `cause_findings.${index}.affected_case_count`),
        evidence: stringLiteral(finding.evidence, ['DIRECT_EVALUATOR_SIGNAL', 'NO_SIGNAL_IN_CURRENT_REPORT'] as const, `cause_findings.${index}.evidence`),
        conclusion: requiredText(finding.conclusion, `cause_findings.${index}.conclusion`),
        recommendedVerification: requiredText(finding.recommended_verification, `cause_findings.${index}.recommended_verification`),
        automaticChangeAllowed: exactFalse(finding.automatic_change_allowed, `cause_findings.${index}.automatic_change_allowed`)
      }
    }),
    recommendations: requiredList(data.recommendations, 'recommendations').map((item, index) => {
      const recommendation = requiredRecord(item, `recommendations.${index}`)
      return {
        priority: stringLiteral(recommendation.priority, ['P0', 'P1', 'P2'] as const, `recommendations.${index}.priority`),
        category: qualityCategory(recommendation.category, `recommendations.${index}.category`),
        recommendation: requiredText(recommendation.recommendation, `recommendations.${index}.recommendation`),
        rationale: requiredText(recommendation.rationale, `recommendations.${index}.rationale`),
        automaticChangeAllowed: exactFalse(recommendation.automatic_change_allowed, `recommendations.${index}.automatic_change_allowed`)
      }
    }),
    rawContentExposed: exactFalse(data.raw_content_exposed, 'raw_content_exposed'),
    modelOrPromptChanged: exactFalse(data.model_or_prompt_changed, 'model_or_prompt_changed')
  }
}
