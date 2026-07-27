import { RagAdapterError } from './ragAdapter'
import {
  AI_MODULE_STATUSES,
  type AiCapabilityDetail,
  type AiEvaluation,
  type AiLatestEvaluation,
  type AiModuleStatus,
  type AiModuleSummary,
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
