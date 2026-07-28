import axios, { AxiosError } from 'axios'

export interface HealthResponse {
  status: 'ok'
  service: string
  version: string
  request_id: string
}

export type BatchStatus =
  | 'RECEIVED'
  | 'PARSING'
  | 'VALIDATED'
  | 'READY_FOR_REVIEW'
  | 'REJECTED'
  | 'FAILED'

export type RowStatus = 'VALID' | 'INVALID' | 'DUPLICATE' | 'CONFLICT'

export interface ValidationIssue {
  error_code: string
  message: string
  row_number: number
  field: string | null
  raw_value: unknown
  suggestion: string
}

export interface ImportBatch {
  id: string
  batch_id: string
  tenant_id: string
  import_type: string
  original_filename: string
  file_sha256: string
  status: BatchStatus
  total_rows: number
  valid_rows: number
  invalid_rows: number
  duplicate_rows: number
  created_at: string
  completed_at: string | null
  created_by: string
  error_message: string | null
  staged_rows?: number
}

export interface ImportRow {
  id: number
  batch_id: string
  source_row_number: number
  raw_data: Record<string, unknown>
  normalized_data: Record<string, unknown>
  row_hash: string
  validation_status: RowStatus
  errors: ValidationIssue[]
  warnings: ValidationIssue[]
}

export interface PreflightIssueSummary {
  code: string
  count: number
  message: string
}

export interface ProductSkuPreflight {
  original_filename: string
  file_sha256: string
  file_size_bytes: number
  worksheets: string[]
  data_row_count: number
  valid_rows: number
  invalid_rows: number
  duplicate_rows: number
  conflict_rows: number
  missing_columns: string[]
  unknown_columns: string[]
  formula_cell_count: number
  hidden_sheet_warnings: string[]
  blank_row_count: number
  error_summary: PreflightIssueSummary[]
  warning_summary: PreflightIssueSummary[]
  can_import: boolean
}

export interface PackageIssue {
  code: string
  message: string
}

export interface TestPackagePreflight {
  original_filename: string
  file_sha256: string
  file_size_bytes: number
  package_id: string
  package_name: string
  version: string
  schema_version: string
  tenant_id: string
  platform: string
  store_code: string
  test_data_mode: boolean
  production_usable: boolean
  response_mode: string
  allow_auto_send: boolean
  worksheets: string[]
  counts: Record<string, number>
  warnings: PackageIssue[]
  errors: PackageIssue[]
  can_import: boolean
}

export interface TestPackageSummary {
  package_id: string
  package_name: string
  version: string
  schema_version: string
  tenant_id: string
  platform: string
  store_code: string
  test_data_mode: boolean
  production_usable: boolean
  response_mode: string
  allow_auto_send: boolean
  import_status: string
  original_filename: string
  zip_sha256: string
  counts: Record<string, number>
  imported_at: string
}

export interface Page<T> {
  items: T[]
  page: number
  page_size: number
  total: number
}

export interface ItemList<T> {
  items: T[]
  total: number
}

export const API_BASE_URL = import.meta.env.VITE_PLATFORM_API_BASE_URL || '/platform-api'
export const AI_API_BASE_URL = import.meta.env.VITE_AI_API_BASE_URL || '/ai-api'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
})

const aiClient = axios.create({
  baseURL: AI_API_BASE_URL,
  timeout: 30000,
})

type OptionalQueryParam = string | number | undefined

/**
 * Omit an unselected filter instead of serializing it as an empty enum value.
 *
 * FastAPI correctly rejects values such as `review_status=` because an empty
 * string is not a member of the review-status enum.  The Admin filter forms
 * represent their "all" choice with an empty string, so normalize that UI
 * state at the client boundary before sending the request.
 */
export function omitBlankQueryParams(
  params?: Record<string, OptionalQueryParam>,
): Record<string, string | number> | undefined {
  if (!params) return undefined

  const normalized = Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== '' && value !== undefined),
  ) as Record<string, string | number>

  return Object.keys(normalized).length > 0 ? normalized : undefined
}

export interface AdminPage<T> {
  items: T[]
  page: number
  size: number
  total: number
}

export interface AdminOverview {
  counts: {
    stores: number
    products: number
    skus: number
    faqs: number
    safety_rules: number
    sources: number
    conflicts: number
    import_batches: number
    suggestions: Record<'submitted' | 'reviewing' | 'planned' | 'done' | 'rejected', number>
  }
  recent_imported_at: string | null
  test_data_mode: boolean
  production_usable: boolean
}

export interface AdminStore {
  store_code: string
  store_name: string
  platform: string
  test_data_mode: boolean
  product_count: number
}

export interface AdminProduct {
  product_id: string
  store_code: string
  platform: string
  product_name_official: string
  product_name_display: string
  sales_status: string
  age_min: number | null
  age_max: number | null
  safety_summary: string | null
  review_status: string
  publishable: boolean
  source_ids: string[]
  test_data_mode: boolean
  production_usable: boolean
}

export interface AdminProductDetail extends AdminProduct {
  sku_count: number
}

export interface AdminSku {
  sku_id: string
  product_id: string
  sku_code: string
  sku_name_official: string
  sku_name_display: string
  relation_type: string
  canonical_sku_id: string | null
  reference_sku_id: string | null
  component_sku_refs: string[]
  publishable: boolean
  source_ids: string[]
  test_data_mode: boolean
  production_usable: boolean
}

export interface AdminFaq {
  faq_id: string
  store_code: string
  product_id: string | null
  sku_id: string | null
  question: string
  recommended_reply: string
  answer_action: string
  risk_level: string
  source_ids: string[]
  test_data_mode: boolean
  production_usable: boolean
}

export interface AdminSafetyRule {
  rule_id: string
  store_code: string
  scenario: string
  risk_level: string
  action: string | null
  forbidden_claim: string | null
  source_ids: string[]
  test_data_mode: boolean
  production_usable: boolean
}

export interface AdminSource {
  source_id: string
  source_type: string
  file_name: string | null
  file_sha256: string | null
  relative_path: string | null
  product_id: string | null
  sku_id: string | null
  test_data_mode: boolean
  production_usable: boolean
}

export interface AdminConflict {
  issue_id: string
  entity_type: string
  entity_id: string
  field_name: string
  value_a: string | null
  value_b: string | null
  source_ids: string[]
  status: string
  decision: string | null
  test_data_mode: boolean
  production_usable: boolean
}

export interface AdminImportBatch {
  id: string
  import_type: string
  original_filename: string
  status: string
  created_at: string
  completed_at: string | null
  test_data_mode: boolean
}

export type SuggestionStatus = 'SUBMITTED' | 'REVIEWING' | 'PLANNED' | 'DONE' | 'REJECTED'

export interface AdminSuggestion {
  id: string
  reporter_id: string
  reporter_name: string | null
  store_code: string | null
  module_key: string | null
  category: string | null
  title: string
  description: string
  frequency: string | null
  urgency: string | null
  status: SuggestionStatus
  internal_note: string | null
  created_at: string
  updated_at: string
}

export type AdminResource =
  | 'stores'
  | 'products'
  | 'faqs'
  | 'safety-rules'
  | 'sources'
  | 'conflicts'
  | 'import-batches'

export async function getAdminOverview(): Promise<AdminOverview> {
  const response = await apiClient.get<AdminOverview>('/api/v1/admin/overview')
  return response.data
}

export async function listAdminResource<T>(
  resource: AdminResource,
  params?: Record<string, string | number | undefined>,
): Promise<AdminPage<T>> {
  const response = await apiClient.get<AdminPage<T>>(`/api/v1/admin/${resource}`, { params })
  return response.data
}

export async function getAdminProduct(productId: string): Promise<AdminProductDetail> {
  const response = await apiClient.get<AdminProductDetail>(
    `/api/v1/admin/products/${encodeURIComponent(productId)}`,
  )
  return response.data
}

export async function listAdminProductSkus(productId: string): Promise<AdminPage<AdminSku>> {
  const response = await apiClient.get<AdminPage<AdminSku>>(
    `/api/v1/admin/products/${encodeURIComponent(productId)}/skus`,
  )
  return response.data
}

export async function listAdminSuggestions(
  params?: Record<string, string | number | undefined>,
): Promise<AdminPage<AdminSuggestion>> {
  const response = await apiClient.get<AdminPage<AdminSuggestion>>(
    '/api/v1/admin/customer-suggestions',
    { params },
  )
  return response.data
}

export async function updateAdminSuggestion(
  suggestionId: string,
  update: { status?: SuggestionStatus; internal_note?: string | null },
): Promise<AdminSuggestion> {
  const response = await apiClient.patch<AdminSuggestion>(
    `/api/v1/admin/customer-suggestions/${encodeURIComponent(suggestionId)}`,
    update,
  )
  return response.data
}

export type ExperienceCaseReviewStatus = 'NEW' | 'REVIEWING' | 'APPROVED' | 'REJECTED'
export type ExperienceCaseFeedbackType = 'ADOPTED' | 'EDITED_ADOPTED' | 'CORRECTION' | 'ESCALATED'
export type ExperienceCaseEvaluationStatus = 'NOT_EXPORTED' | 'EXPORTED' | 'EVALUATED' | 'WRITEBACK_REJECTED'

export interface AdminExperienceCase {
  case_id: string
  revision: number
  source_type: string
  store_code: string
  product_id: string | null
  sku_id: string | null
  question: string
  ai_answer: string
  final_answer: string
  feedback_type: ExperienceCaseFeedbackType
  created_by: string
  review_status: ExperienceCaseReviewStatus
  review_note: string | null
  reviewed_by: string | null
  reviewed_at: string | null
  export_revision: string | null
  content_hash: string | null
  redaction_version: string
  evaluation_status: ExperienceCaseEvaluationStatus
  latest_evaluation_run_id: string | null
  created_at: string
  updated_at: string
}

export interface ExperienceCaseEvaluation {
  evaluation_run_id: string
  case_id: string
  revision: number
  export_revision: string
  evaluation_status: ExperienceCaseEvaluationStatus
  model_version: string
  prompt_version: string
  result: Record<string, unknown>
  suggestions: Array<Record<string, unknown>>
  recorded_at: string
}

export interface AiOptimizationCase {
  case_id: string
  revision: number
  store_code: string
  product_id: string | null
  sku_id: string | null
  question: string
  ai_answer: string
  final_answer: string
  feedback_type: ExperienceCaseFeedbackType
  export_revision: string
  content_hash: string
  evaluation_status: ExperienceCaseEvaluationStatus
  latest_evaluation_run_id: string | null
  latest_evaluation: ExperienceCaseEvaluation | null
}

export type AiResponseFeedbackType = 'FACT_ERROR' | 'MISSING_INFO' | 'STYLE_ISSUE' | 'RISK_ISSUE' | 'OTHER'
export type AiResponseFeedbackAnalysisStatus = 'ANALYZED'

export interface AiFeedbackAnalysisResult {
  feedback_id: string
  revision: number
  content_hash: string
  feedback_type: AiResponseFeedbackType
  analysis_run_id: string
  analysis_status: AiResponseFeedbackAnalysisStatus
  model_version: string
  prompt_version: string
  analysis: Record<string, unknown>
  suggestions: Array<Record<string, unknown>>
  created_at: string
  question: string
  ai_answer: string
  final_answer: string | null
}

export interface AiFeedbackAnalysisResultList {
  items: AiFeedbackAnalysisResult[]
  total: number
}

export async function listAdminExperienceCases(
  params?: Record<string, string | number | undefined>,
): Promise<AdminPage<AdminExperienceCase>> {
  const response = await apiClient.get<AdminPage<AdminExperienceCase>>(
    '/api/v1/admin/customer-experience-cases',
    { params: omitBlankQueryParams(params) },
  )
  return response.data
}

export async function getAdminExperienceCase(caseId: string): Promise<AdminExperienceCase> {
  const response = await apiClient.get<AdminExperienceCase>(
    `/api/v1/admin/customer-experience-cases/${encodeURIComponent(caseId)}`,
  )
  return response.data
}

export async function updateAdminExperienceCaseReview(
  caseId: string,
  update: {
    review_status: ExperienceCaseReviewStatus
    review_note?: string | null
    reviewed_by?: string | null
  },
): Promise<AdminExperienceCase> {
  const response = await apiClient.patch<AdminExperienceCase>(
    `/api/v1/admin/customer-experience-cases/${encodeURIComponent(caseId)}/review`,
    update,
  )
  return response.data
}

export async function listAiOptimizationCases(
  params?: Record<string, string | number | undefined>,
): Promise<AdminPage<AiOptimizationCase>> {
  const response = await apiClient.get<AdminPage<AiOptimizationCase>>(
    '/api/v1/admin/ai-optimization/cases',
    { params: omitBlankQueryParams(params) },
  )
  return response.data
}

export async function listAiFeedbackAnalysisResults(): Promise<AiFeedbackAnalysisResultList> {
  const response = await apiClient.get<AiFeedbackAnalysisResultList>(
    '/api/v1/admin/ai-quality/analysis-results',
  )
  return response.data
}

export interface AiModule {
  id: string
  name: string
  status: string
  description: string | null
  implemented: boolean
  promptMetadata: Record<string, unknown> | null
  recentEvaluations: unknown[]
}

export interface AiRuntimeStatus {
  ready: boolean
  modelConfigured: boolean
  initializationError: string | null
}

export interface AiKnowledgeStatistics {
  documentCount: number
  chunkCount: number
  collectionName: string
  embeddingModel: string
  vectorDatabase: string
  modelConfigured: boolean
}

export interface AiModuleDetail extends AiModule {
  modelProvider: string | null
  modelName: string | null
  ready: boolean | null
  modelConfigured: boolean | null
  initializationError: string | null
  knowledgeCount: number | null
  promptVersion: string | null
  promptHash: string | null
  safePreview: string | null
  metricsScope: string | null
  callCount: number | null
  successCount: number | null
  errorCount: number | null
  averageLatencyMs: number | null
  lastCalledAt: string | null
  lastErrorSummary: string | null
  supportedActions: string[]
  raw: Record<string, unknown>
}

export interface AiPromptMetadata {
  moduleId: string
  status: string | null
  promptVersion: string | null
  promptHash: string | null
  updatedAt: string | null
  sourceType: string | null
  safePreview: string | null
  raw: Record<string, unknown>
}

export interface AiLatestEvaluation {
  moduleId: string
  status: string
  evaluation: {
    evaluationId: string | null
    executedAt: string | null
    datasetVersion: string | null
    totalCases: number | null
    passedCases: number | null
    passRate: number | null
    checks: Record<string, number | null>
    failedCaseIds: string[]
    reportAvailable: boolean
  } | null
  raw: Record<string, unknown>
}

function normalizeAiModule(value: unknown, index: number): AiModule {
  const row = typeof value === 'object' && value !== null ? value as Record<string, unknown> : {}
  const text = (key: string, fallback: string): string => typeof row[key] === 'string' ? row[key] : fallback
  return {
    id: text('module_id', text('id', `module-${index + 1}`)),
    name: text('display_name', text('name', text('module_key', `Module ${index + 1}`))),
    status: text('status', 'UNKNOWN'),
    description: typeof row.description === 'string' ? row.description : null,
    implemented: row.implemented === true,
    promptMetadata: typeof row.prompt_metadata === 'object' && row.prompt_metadata !== null
      ? row.prompt_metadata as Record<string, unknown>
      : null,
    recentEvaluations: Array.isArray(row.recent_evaluations) ? row.recent_evaluations : [],
  }
}

function aiEnvelopeData<T>(payload: unknown): T {
  if (typeof payload !== 'object' || payload === null) {
    throw new Error('AI 服务返回的不是可识别的响应。')
  }
  const envelope = payload as { success?: unknown; data?: unknown }
  if (envelope.success !== true || envelope.data === undefined || envelope.data === null) {
    throw new Error('AI 服务未返回成功的数据包。')
  }
  return envelope.data as T
}

/**
 * The sole A-line path declared by ai-control.v1. This adapter consumes only
 * the A success envelope's `data.modules` field and never fabricates modules.
 */
export async function listAiModules(): Promise<AiModule[]> {
  const response = await aiClient.get<unknown>('/api/admin/ai/modules')
  const data = aiEnvelopeData<{ modules?: unknown }>(response.data)
  if (!Array.isArray(data.modules)) throw new Error('AI 服务未返回模块列表。')
  return data.modules.map(normalizeAiModule)
}

function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === 'object' && value !== null ? value as Record<string, unknown> : {}
}

function optionalText(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function optionalNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

export async function getAiRuntimeStatus(): Promise<AiRuntimeStatus> {
  const response = await aiClient.get<unknown>('/api/status')
  const data = asRecord(aiEnvelopeData<unknown>(response.data))
  return {
    ready: data.ready === true,
    modelConfigured: data.model_configured === true,
    initializationError: optionalText(data.initialization_error),
  }
}

export async function getAiKnowledgeStatistics(): Promise<AiKnowledgeStatistics> {
  const response = await aiClient.get<unknown>('/api/knowledge/statistics')
  const data = asRecord(aiEnvelopeData<unknown>(response.data))
  const documentCount = optionalNumber(data.document_count)
  const chunkCount = optionalNumber(data.chunk_count)
  if (documentCount === null || chunkCount === null) {
    throw new Error('AI 服务未返回可用的知识统计。')
  }
  return {
    documentCount,
    chunkCount,
    collectionName: optionalText(data.collection_name) ?? '未提供',
    embeddingModel: optionalText(data.embedding_model) ?? '未提供',
    vectorDatabase: optionalText(data.vector_database) ?? '未提供',
    modelConfigured: data.model_configured === true,
  }
}

export async function getAiModuleDetail(moduleId: string): Promise<AiModuleDetail> {
  const response = await aiClient.get<unknown>(`/api/admin/ai/modules/${encodeURIComponent(moduleId)}`)
  const raw = asRecord(aiEnvelopeData<unknown>(response.data))
  const base = normalizeAiModule(raw, 0)
  const actions = Array.isArray(raw.supported_actions)
    ? raw.supported_actions.filter((item): item is string => typeof item === 'string')
    : []
  return {
    ...base,
    modelProvider: optionalText(raw.model_provider),
    modelName: optionalText(raw.model_name),
    ready: typeof raw.ready === 'boolean' ? raw.ready : null,
    modelConfigured: typeof raw.model_configured === 'boolean' ? raw.model_configured : null,
    initializationError: optionalText(raw.initialization_error),
    knowledgeCount: optionalNumber(raw.knowledge_count),
    promptVersion: optionalText(raw.prompt_version),
    promptHash: optionalText(raw.prompt_hash),
    safePreview: optionalText(raw.safe_preview),
    metricsScope: optionalText(raw.metrics_scope),
    callCount: optionalNumber(raw.call_count),
    successCount: optionalNumber(raw.success_count),
    errorCount: optionalNumber(raw.error_count),
    averageLatencyMs: optionalNumber(raw.average_latency_ms),
    lastCalledAt: optionalText(raw.last_called_at),
    lastErrorSummary: optionalText(raw.last_error_summary),
    supportedActions: actions,
    raw,
  }
}

export async function getAiModulePrompt(moduleId: string): Promise<AiPromptMetadata> {
  const response = await aiClient.get<unknown>(`/api/admin/ai/modules/${encodeURIComponent(moduleId)}/prompt`)
  const raw = asRecord(aiEnvelopeData<unknown>(response.data))
  return {
    moduleId: optionalText(raw.module_id) ?? moduleId,
    status: optionalText(raw.status),
    promptVersion: optionalText(raw.prompt_version),
    promptHash: optionalText(raw.prompt_hash),
    updatedAt: optionalText(raw.updated_at),
    sourceType: optionalText(raw.source_type),
    safePreview: optionalText(raw.safe_preview),
    raw,
  }
}

export async function getAiModuleLatestEvaluation(moduleId: string): Promise<AiLatestEvaluation> {
  const response = await aiClient.get<unknown>(`/api/admin/ai/modules/${encodeURIComponent(moduleId)}/evaluations/latest`)
  const raw = asRecord(aiEnvelopeData<unknown>(response.data))
  const evaluationValue = asRecord(raw.evaluation)
  const hasEvaluation = raw.evaluation !== null && Object.keys(evaluationValue).length > 0
  const checksValue = asRecord(evaluationValue.checks)
  const checks = Object.fromEntries(
    Object.entries(checksValue).map(([key, value]) => [key, optionalNumber(value)]),
  )
  return {
    moduleId: optionalText(raw.module_id) ?? moduleId,
    status: optionalText(raw.status) ?? 'UNKNOWN',
    evaluation: hasEvaluation ? {
      evaluationId: optionalText(evaluationValue.evaluation_id),
      executedAt: optionalText(evaluationValue.executed_at),
      datasetVersion: optionalText(evaluationValue.dataset_version),
      totalCases: optionalNumber(evaluationValue.total_cases),
      passedCases: optionalNumber(evaluationValue.passed_cases),
      passRate: optionalNumber(evaluationValue.pass_rate),
      checks,
      failedCaseIds: Array.isArray(evaluationValue.failed_case_ids)
        ? evaluationValue.failed_case_ids.filter((item): item is string => typeof item === 'string')
        : [],
      reportAvailable: evaluationValue.report_available === true,
    } : null,
    raw,
  }
}

export async function getHealth(): Promise<HealthResponse> {
  const response = await apiClient.get<HealthResponse>('/health')
  return response.data
}

export function isOfflineError(error: unknown): boolean {
  return error instanceof AxiosError && error.response === undefined
}

export async function listImportBatches(): Promise<Page<ImportBatch>> {
  const response = await apiClient.get<Page<ImportBatch>>('/api/v1/import-batches')
  return response.data
}

export async function getImportBatch(batchId: string): Promise<ImportBatch> {
  const response = await apiClient.get<ImportBatch>(`/api/v1/import-batches/${batchId}`)
  return response.data
}

export async function listImportRows(
  batchId: string,
  status?: RowStatus,
): Promise<Page<ImportRow>> {
  const response = await apiClient.get<Page<ImportRow>>(
    `/api/v1/import-batches/${batchId}/rows`,
    { params: status ? { status } : undefined },
  )
  return response.data
}

export async function uploadProductSku(
  file: File,
  onProgress?: (percent: number) => void,
): Promise<ImportBatch> {
  const form = new FormData()
  form.append('file', file)
  form.append('created_by', 'admin-web-manual-import')
  const response = await apiClient.post<ImportBatch>(
    '/api/v1/import-batches/product-sku',
    form,
    {
      onUploadProgress: (event) => {
        if (event.total && onProgress) {
          onProgress(Math.round((event.loaded * 100) / event.total))
        }
      },
    },
  )
  return response.data
}

export async function preflightProductSku(file: File): Promise<ProductSkuPreflight> {
  const form = new FormData()
  form.append('file', file)
  const response = await apiClient.post<ProductSkuPreflight>(
    '/api/v1/import-batches/product-sku/preflight',
    form,
  )
  return response.data
}

export async function listTestDataPackages(): Promise<ItemList<TestPackageSummary>> {
  const response = await apiClient.get<ItemList<TestPackageSummary>>('/api/v1/test-data-packages')
  return response.data
}

export async function preflightTestDataPackage(file: File): Promise<TestPackagePreflight> {
  const form = new FormData()
  form.append('file', file)
  const response = await apiClient.post<TestPackagePreflight>(
    '/api/v1/test-data-packages/preflight',
    form,
  )
  return response.data
}

export async function importTestDataPackage(file: File): Promise<TestPackageSummary> {
  const form = new FormData()
  form.append('file', file)
  form.append('imported_by', 'admin-web-test-import')
  const response = await apiClient.post<TestPackageSummary>('/api/v1/test-data-packages', form)
  return response.data
}

export function productSkuTemplateUrl(): string {
  return `${API_BASE_URL}/api/v1/import-templates/product-sku`
}

export function errorReportUrl(batchId: string): string {
  return `${API_BASE_URL}/api/v1/import-batches/${encodeURIComponent(batchId)}/errors`
}

export function apiErrorMessage(error: unknown): string {
  if (isOfflineError(error)) return '无法连接运营平台。请确认本机服务已启动后再重试。'
  if (error instanceof AxiosError) {
    const status = error.response?.status
    if (status === 400 || status === 422) return '筛选条件或提交内容不符合要求。请检查页面中的必填项和格式。'
    if (status === 401 || status === 403) return '当前试运行账号没有访问此项数据的权限。请联系管理员确认。'
    if (status === 404) return '没有找到所需记录。请刷新页面并确认筛选条件。'
    if (status === 409) return '这条记录的状态已发生变化。请刷新后再核对和操作。'
    if (status !== undefined && status >= 500) return '运营平台暂时无法处理请求。请稍后重试；若持续出现，请查看服务状态。'
  }
  return '暂时无法完成此操作。请稍后重试；若持续出现，请查看服务状态。'
}
