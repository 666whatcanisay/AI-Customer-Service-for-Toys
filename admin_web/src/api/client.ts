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
  target_store_code: string | null
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
  recognized_product_count: number
  recognized_sku_count: number
  rows_needing_manual_completion: number
  missing_field_counts: Record<string, number>
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

export type TrialActorId = 'trial-admin' | 'trial-operator' | 'trial-support'
export type TrialAuditReason = 'DAILY_OPERATIONS' | 'CASE_REVIEW' | 'KNOWLEDGE_MAINTENANCE' | 'GOVERNANCE_REVIEW'

const TRIAL_ACTOR_STORAGE_KEY = 'mumu.trial-actor'
const TRIAL_REASON_STORAGE_KEY = 'mumu.trial-reason'

function storedValue(key: string, fallback: string): string {
  if (typeof window === 'undefined') return fallback
  return window.localStorage.getItem(key) || fallback
}

export function getTrialActor(): TrialActorId {
  const actor = storedValue(TRIAL_ACTOR_STORAGE_KEY, 'trial-operator')
  return actor === 'trial-admin' || actor === 'trial-support' ? actor : 'trial-operator'
}

export function setTrialActor(actor: TrialActorId): void {
  window.localStorage.setItem(TRIAL_ACTOR_STORAGE_KEY, actor)
}

export function getTrialAuditReason(): TrialAuditReason {
  const reason = storedValue(TRIAL_REASON_STORAGE_KEY, 'DAILY_OPERATIONS')
  return reason === 'CASE_REVIEW' || reason === 'KNOWLEDGE_MAINTENANCE' || reason === 'GOVERNANCE_REVIEW'
    ? reason
    : 'DAILY_OPERATIONS'
}

export function setTrialAuditReason(reason: TrialAuditReason): void {
  window.localStorage.setItem(TRIAL_REASON_STORAGE_KEY, reason)
}

apiClient.interceptors.request.use((config) => {
  config.headers.set('X-Platform-Trial-Actor', getTrialActor())
  config.headers.set('X-Platform-Reason', getTrialAuditReason())
  return config
})

const aiClient = axios.create({
  baseURL: AI_API_BASE_URL,
  timeout: 30000,
})

function queryParams(
  params?: Record<string, string | number | undefined>,
): Record<string, string | number> | undefined {
  if (!params) return undefined
  return Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== '' && value !== undefined),
  ) as Record<string, string | number>
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
  | 'skus'
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
  const response = await apiClient.get<AdminPage<T>>(`/api/v1/admin/${resource}`, { params: queryParams(params) })
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
    { params: queryParams(params) },
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

export interface CustomerEfficiencySummary {
  summary_version: string
  generated_at: string
  window_start: string
  window_end: string
  ai_request_count: number
  direct_adoption_count: number
  edited_adoption_count: number
  not_adopted_count: number
  adoption_rate: number
}

export interface AdminOperationsToday {
  today: {
    generated_at: string
    window_start: string
    window_end: string
    ai_request_count: number
    direct_adoption_count: number
    edited_adoption_count: number
    not_adopted_count: number
    adoption_rate: number
    experience_case_submission_count: number
    ai_feedback_submission_count: number
    completed_ai_analysis_count: number
  }
  work_queue: {
    pending_experience_review_count: number
    pending_ai_analysis_count: number
    open_knowledge_conflict_count: number
  }
  knowledge: {
    store_count: number
    product_count: number
    sku_count: number
    faq_count: number
    safety_rule_count: number
    recent_imported_at: string | null
  }
  test_data_mode: boolean
  production_usable: boolean
}

export interface TrialGovernanceStatus {
  actor_id: string
  role: 'ADMIN' | 'OPERATOR' | 'SUPPORT'
  capabilities: string[]
  access_boundary_mode: string
  formal_authentication_enabled: boolean
  formal_authorization_enabled: boolean
  audit_foundation_enabled: boolean
  automatic_redaction_enabled: boolean
  retention_policy_configured: boolean
  current_redaction_marker: string
  test_data_mode: boolean
  production_usable: boolean
}

export interface TrialAuditEvent {
  id: string
  occurred_at: string
  actor_id: string
  actor_role: string
  action: string
  resource_type: string
  resource_id: string
  outcome: string
  reason_code: string
  metadata: Record<string, string | number | boolean>
}

export interface TrialAuditEventList {
  items: TrialAuditEvent[]
  total: number
  page: number
  size: number
}

export type PilotStoreSetupStatus = 'NEEDS_PRODUCT_IMPORT' | 'NEEDS_KNOWLEDGE' | 'OBSERVABLE'

export interface PilotStore {
  store_code: string
  store_name: string
  platform: string
  created_at: string
  setup_status: PilotStoreSetupStatus
  catalog_product_count: number
  catalog_sku_count: number
  staged_product_count: number
  staged_sku_count: number
  faq_count: number
  safety_rule_count: number
  experience_case_count: number
  ai_feedback_count: number
  latest_product_imported_at: string | null
  test_data_mode: boolean
  production_usable: boolean
}

export async function listAdminExperienceCases(
  params?: Record<string, string | number | undefined>,
): Promise<AdminPage<AdminExperienceCase>> {
  const response = await apiClient.get<AdminPage<AdminExperienceCase>>(
    '/api/v1/admin/customer-experience-cases',
    { params: queryParams(params) },
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
    { params: queryParams(params) },
  )
  return response.data
}

export async function listAiFeedbackAnalysisResults(): Promise<AiFeedbackAnalysisResultList> {
  const response = await apiClient.get<AiFeedbackAnalysisResultList>(
    '/api/v1/admin/ai-quality/analysis-results',
  )
  return response.data
}

export async function getAdminCustomerEfficiencySummary(): Promise<CustomerEfficiencySummary> {
  const response = await apiClient.get<CustomerEfficiencySummary>(
    '/api/v1/admin/customer-efficiency/summary',
  )
  return response.data
}

/** C-internal landing-page projection. It returns metrics and timestamps only. */
export async function getAdminOperationsToday(): Promise<AdminOperationsToday> {
  const response = await apiClient.get<AdminOperationsToday>('/api/v1/admin/operations/today')
  return response.data
}

export async function getTrialGovernance(): Promise<TrialGovernanceStatus> {
  const response = await apiClient.get<TrialGovernanceStatus>('/api/v1/admin/trial-governance')
  return response.data
}

export async function listTrialAuditEvents(): Promise<TrialAuditEventList> {
  const response = await apiClient.get<TrialAuditEventList>('/api/v1/admin/trial-governance/audit-events')
  return response.data
}

export async function listPilotStores(): Promise<{ items: PilotStore[]; total: number }> {
  const response = await apiClient.get<{ items: PilotStore[]; total: number }>('/api/v1/admin/pilot-stores')
  return response.data
}

export async function createPilotStore(payload: {
  store_code: string
  store_name: string
  platform: string
}): Promise<PilotStore> {
  const response = await apiClient.post<PilotStore>('/api/v1/admin/pilot-stores', payload)
  return response.data
}

export interface AiModule {
  id: string
  name: string
  status: string
  description: string | null
  promptMetadata: Record<string, unknown> | null
  recentEvaluations: unknown[]
}

function normalizeAiModule(value: unknown, index: number): AiModule {
  const row = typeof value === 'object' && value !== null ? value as Record<string, unknown> : {}
  const text = (key: string, fallback: string): string => typeof row[key] === 'string' ? row[key] : fallback
  return {
    id: text('module_id', text('id', `module-${index + 1}`)),
    name: text('display_name', text('name', text('module_key', `Module ${index + 1}`))),
    status: text('status', 'UNKNOWN'),
    description: typeof row.description === 'string' ? row.description : null,
    promptMetadata: typeof row.prompt_metadata === 'object' && row.prompt_metadata !== null
      ? row.prompt_metadata as Record<string, unknown>
      : null,
    recentEvaluations: Array.isArray(row.recent_evaluations) ? row.recent_evaluations : [],
  }
}

/**
 * The sole A-line path declared by the task card.  This adapter never
 * fabricates module data when the A branch has not yet been integrated.
 */
export async function listAiModules(): Promise<AiModule[]> {
  const response = await aiClient.get<unknown>('/api/admin/ai/modules')
  const payload = response.data
  const rows = Array.isArray(payload)
    ? payload
    : typeof payload === 'object' && payload !== null && Array.isArray((payload as { items?: unknown }).items)
      ? (payload as { items: unknown[] }).items
      : []
  return rows.map(normalizeAiModule)
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
  targetStoreCode?: string,
): Promise<ImportBatch> {
  const form = new FormData()
  form.append('file', file)
  form.append('created_by', 'admin-web-manual-import')
  if (targetStoreCode) form.append('target_store_code', targetStoreCode)
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

export async function preflightProductSku(
  file: File,
  targetStoreCode?: string,
): Promise<ProductSkuPreflight> {
  const form = new FormData()
  form.append('file', file)
  if (targetStoreCode) form.append('target_store_code', targetStoreCode)
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
  if (isOfflineError(error)) return '无法连接平台服务，请检查网络或服务状态。'
  if (error instanceof AxiosError) {
    const status = error.response?.status
    const data = error.response?.data as { error?: { code?: unknown; message?: unknown } } | undefined
    const code = data?.error?.code
    if (code === 'TRIAL_ROLE_FORBIDDEN' || code === 'TRIAL_ACTOR_UNKNOWN') {
      return '当前试运行角色没有此操作权限。请切换到有权限的角色，或联系管理员。'
    }
    if (status === 400 || status === 422) {
      return '提交内容不完整或格式不正确。请检查必填项、筛选条件和输入格式后重试。'
    }
    if (status === 403 || status === 401) {
      return '当前试运行角色没有访问权限。请联系管理员确认权限边界。'
    }
    if (status === 404) {
      return '未找到所需数据。请检查链接或筛选条件，必要时先完成数据同步。'
    }
    if (status === 409) {
      return '数据存在冲突或状态已变化。请刷新后核对当前记录再重试。'
    }
    const message = data?.error?.message
    if (typeof message === 'string' && /[\u3400-\u9fff]/.test(message)) return message
  }
  return '请求失败，请稍后重试。'
}
