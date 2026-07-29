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

export type KnowledgeMaterialType = 'PRODUCT_SPEC' | 'SAFETY_INSTRUCTION' | 'ASSEMBLY_GUIDE' | 'FAQ_SOURCE' | 'OTHER'
export type KnowledgeTemplateType = 'PRODUCT_KNOWLEDGE' | 'SKU_DIFFERENCE' | 'FAQ' | 'SAFETY_RULE' | 'AI_FEEDBACK' | 'KNOWLEDGE_GAP'
export type KnowledgeMaterialStatus = 'RECEIVED' | 'RECOGNIZED' | 'REVIEWING' | 'APPROVED_FOR_ANALYSIS' | 'ANALYZING' | 'ANALYZED' | 'ANALYSIS_FAILED' | 'REJECTED'
export type KnowledgeQualityOverallStatus = 'ANALYZED' | 'FAILED'
export type KnowledgeQualityGapSeverity = 'LOW' | 'MEDIUM' | 'HIGH'
export type KnowledgeQualityGapStatus = 'OPEN' | 'ACKNOWLEDGED' | 'RESOLVED' | 'DISMISSED'

export interface RecognitionSummary {
  readable: boolean
  file_extension: string
  detected_fields: string[]
  missing_expected_fields: string[]
  privacy_reminder: string
  template_type: KnowledgeTemplateType | null
  template_name: string | null
  record_count: number
  warnings: string[]
  high_risk_source_confirmed: boolean | null
}

export interface KnowledgeMaterial {
  material_id: string
  revision: number
  store_code: string
  product_id: string
  sku_id: string | null
  material_type: KnowledgeMaterialType
  display_name: string
  original_filename: string
  content_hash: string
  redaction_version: string
  recognition_summary: RecognitionSummary
  material_status: KnowledgeMaterialStatus
  submitted_by: string
  reviewed_by: string | null
  reviewed_at: string | null
  review_note: string | null
  created_at: string
  updated_at: string
}

export interface KnowledgeMaterialDetail extends KnowledgeMaterial {
  analysis_text_preview: string
}

export interface KnowledgeMaterialReceipt {
  material_id: string
  revision: number
  content_hash: string
  material_status: KnowledgeMaterialStatus
  recognition_summary: RecognitionSummary
}

export interface KnowledgeMaterialList {
  items: KnowledgeMaterial[]
  total: number
  page: number
  size: number
}

export interface KnowledgeQualityGap {
  gap_id: string
  gap_code: string
  severity: KnowledgeQualityGapSeverity
  title: string
  description: string
  recommended_action: string
  status: KnowledgeQualityGapStatus
}

export interface KnowledgeQualityAssessment {
  assessment_id: string
  material_id: string
  revision: number
  content_hash: string
  analysis_run_id: string
  model_version: string
  prompt_version: string
  overall_status: KnowledgeQualityOverallStatus
  summary: string
  gaps: KnowledgeQualityGap[]
  created_at: string
}

export interface KnowledgeQualityAssessmentList {
  items: KnowledgeQualityAssessment[]
  total: number
}

export type KnowledgeTopicStatus = 'SUPPORTED' | 'PARTIAL' | 'MISSING'
export type ProductKnowledgeState = 'WELL_COVERED' | 'BASIC_AVAILABLE' | 'NEEDS_COMPLETION'
export type KnowledgeDataStatus = 'DRAFT' | 'PENDING_REVIEW' | 'APPROVED'
export type KnowledgeAiStatus = 'EFFECTIVE' | 'PARTIALLY_AVAILABLE' | 'MISSING_KNOWLEDGE' | 'UNCONFIRMED'
export type KnowledgeGapWorkflowStatus = 'PENDING' | 'IN_PROGRESS' | 'PENDING_VERIFICATION' | 'RESOLVED'

export interface ProductKnowledgeTechnicalDetails {
  store_code: string | null
  platform: string | null
  product_id: string | null
  product_code: string | null
  sku_id: string | null
  sku_code: string | null
  source_id: string | null
  material_id: string | null
  revision: number | null
  content_hash: string | null
}

export interface StoreKnowledgeSummary {
  store_name: string
  platform_name: string
  remarks?: string
  product_count: number
  ai_usable_product_count: number
  gap_count: number
  pending_review_count: number
  technical_details: ProductKnowledgeTechnicalDetails
}

export interface ProductKnowledgeOverview {
  generated_at: string
  has_data: boolean
  stats: {
    store_count: number | null
    product_count: number | null
    ai_usable_product_count: number | null
    gap_count: number | null
    pending_review_count: number | null
  }
  stores: StoreKnowledgeSummary[]
  boundary_note: string
}

export interface ProductKnowledgeListItem {
  store_name: string
  product_name: string
  product_summary: string | null
  core_selling_points: string[]
  applicable_age: string | null
  material_safety: string | null
  package_contents: string | null
  faq_count: number
  sku_names: string[]
  coverage_percent: number
  ai_usable: boolean
  knowledge_state: ProductKnowledgeState
  data_status: KnowledgeDataStatus
  ai_status: KnowledgeAiStatus
  answerable_topics: string[]
  missing_topics: string[]
  gap_count: number
  technical_details: ProductKnowledgeTechnicalDetails
}

export interface TopicCoverage {
  key: string
  name: string
  level: 'A' | 'B'
  status: KnowledgeTopicStatus
  evidence_summary: string | null
}

export interface ProductKnowledgeGap {
  key: string
  title: string
  severity: string
  description: string
  recommended_action: string
  safe_fallback: string
  source: string
}

export interface ProductKnowledgeDetail {
  store: StoreKnowledgeSummary
  product: {
    product_name: string
    product_summary: string | null
    core_selling_points: string[]
    applicable_age: string | null
    material: string | null
    package_contents: string | null
    usage_instructions: string | null
    technical_details: ProductKnowledgeTechnicalDetails
  }
  skus: Array<{
    sku_name: string
    color_style: string | null
    specification_difference: string | null
    package_difference: string | null
    faq_count: number
    difference_confirmed: boolean
    attributes: string[]
    technical_details: ProductKnowledgeTechnicalDetails
  }>
  faqs: Array<{
    question: string
    recommended_reply: string
    answer_strategy: string
    risk_level: string
    sku_name: string | null
  }>
  safety_information: Array<{
    title: string
    content: string
    risk_level: string | null
    forbidden_claim: string | null
    handoff_condition: string | null
  }>
  sources: Array<{
    source_name: string
    source_type: string
    review_status: string | null
    technical_details: ProductKnowledgeTechnicalDetails
  }>
  coverage_percent: number
  ai_usable: boolean
  knowledge_state: ProductKnowledgeState
  data_status: KnowledgeDataStatus
  ai_status: KnowledgeAiStatus
  topic_coverage: TopicCoverage[]
  answerable_topics: string[]
  missing_topics: string[]
  gaps: ProductKnowledgeGap[]
  next_actions: string[]
  boundary_note: string
}

export interface ProductKnowledgeGapListItem {
  store_name: string
  product_name: string
  sku_name: string
  missing_topic: string
  occurrence_count: number
  impact_level: string
  priority: 'P0' | 'P1' | 'P2' | 'P3'
  workflow_status: KnowledgeGapWorkflowStatus
  description: string
  recommended_action: string
  safe_fallback: string
}

export async function getProductKnowledgeOverview(): Promise<ProductKnowledgeOverview> {
  const response = await apiClient.get<ProductKnowledgeOverview>(
    '/api/v1/admin/product-knowledge/overview',
  )
  return response.data
}

export async function listProductKnowledgeProducts(
  storeCode?: string,
): Promise<ItemList<ProductKnowledgeListItem>> {
  const response = await apiClient.get<ItemList<ProductKnowledgeListItem>>(
    '/api/v1/admin/product-knowledge/products',
    { params: omitBlankQueryParams({ store_code: storeCode }) },
  )
  return response.data
}

export async function getProductKnowledgeProduct(productId: string): Promise<ProductKnowledgeDetail> {
  const response = await apiClient.get<ProductKnowledgeDetail>(
    `/api/v1/admin/product-knowledge/products/${encodeURIComponent(productId)}`,
  )
  return response.data
}

export type StoreOperationStatus = 'ACTIVE' | 'INACTIVE'

export interface StoreOperationItem {
  store_ref: number
  store_name: string
  platform_name: string
  status: StoreOperationStatus
  status_name: string
  product_count: number
  created_at: string
  remarks: string
}

export interface StoreOperationInput {
  store_name: string
  platform: 'pinduoduo' | 'taobao' | 'tmall' | 'jd' | 'douyin' | 'offline' | 'other'
  remarks: string
}

export interface ProductOperationInput {
  product_name: string
  product_summary: string
}

export interface ProductOperationItem {
  product_ref: string
  store_ref: number
  store_name: string
  product_name: string
  product_summary: string
  data_status: 'PENDING_REVIEW'
  data_status_name: string
  sku_count: number
  created_at: string
}

export async function listOperationStores(): Promise<ItemList<StoreOperationItem>> {
  const response = await apiClient.get<ItemList<StoreOperationItem>>(
    '/api/v1/admin/operations/stores',
  )
  return response.data
}

export async function createOperationStore(
  input: StoreOperationInput,
): Promise<StoreOperationItem> {
  const response = await apiClient.post<StoreOperationItem>(
    '/api/v1/admin/operations/stores',
    input,
  )
  return response.data
}

export async function getOperationStore(storeRef: number): Promise<StoreOperationItem> {
  const response = await apiClient.get<StoreOperationItem>(
    `/api/v1/admin/operations/stores/${storeRef}`,
  )
  return response.data
}

export async function updateOperationStore(
  storeRef: number,
  input: StoreOperationInput & { status: StoreOperationStatus },
): Promise<StoreOperationItem> {
  const response = await apiClient.patch<StoreOperationItem>(
    `/api/v1/admin/operations/stores/${storeRef}`,
    input,
  )
  return response.data
}

export async function createOperationProduct(
  storeRef: number,
  input: ProductOperationInput,
): Promise<ProductOperationItem> {
  const response = await apiClient.post<ProductOperationItem>(
    `/api/v1/admin/operations/stores/${storeRef}/products`,
    input,
  )
  return response.data
}

export async function updateProductBasicInfo(
  productId: string,
  input: {
    product_display_name: string
    product_summary: string
    store_display_name: string
    store_remarks: string
  },
): Promise<ProductKnowledgeDetail> {
  const response = await apiClient.patch<ProductKnowledgeDetail>(
    `/api/v1/admin/operations/products/${encodeURIComponent(productId)}/basic-info`,
    input,
  )
  return response.data
}

export async function listProductKnowledgeGaps(params?: {
  store_code?: string
  priority?: '' | 'P0' | 'P1' | 'P2' | 'P3'
  workflow_status?: '' | KnowledgeGapWorkflowStatus
}): Promise<ItemList<ProductKnowledgeGapListItem>> {
  const response = await apiClient.get<ItemList<ProductKnowledgeGapListItem>>(
    '/api/v1/admin/product-knowledge/gaps',
    { params: omitBlankQueryParams(params) },
  )
  return response.data
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

export async function listKnowledgeMaterials(
  params?: { store_code?: string; product_id?: string; material_status?: KnowledgeMaterialStatus | ''; page?: number; size?: number },
): Promise<KnowledgeMaterialList> {
  const response = await apiClient.get<KnowledgeMaterialList>('/api/v1/admin/knowledge-materials', {
    params: omitBlankQueryParams(params),
  })
  return response.data
}

export async function getKnowledgeMaterial(materialId: string): Promise<KnowledgeMaterialDetail> {
  const response = await apiClient.get<KnowledgeMaterialDetail>(
    `/api/v1/admin/knowledge-materials/${encodeURIComponent(materialId)}`,
  )
  return response.data
}

export async function uploadKnowledgeMaterial(
  file: File,
  fields: {
    store_code: string
    product_id: string
    sku_id?: string
    material_type: KnowledgeMaterialType
    template_type?: KnowledgeTemplateType
    display_name: string
    submitted_by: string
    material_id?: string
  },
): Promise<KnowledgeMaterialReceipt> {
  const form = new FormData()
  form.append('file', file)
  Object.entries(fields).forEach(([key, value]) => {
    if (value) form.append(key, value)
  })
  const idempotencyKey = typeof crypto?.randomUUID === 'function'
    ? crypto.randomUUID()
    : `knowledge-material-${Date.now()}-${Math.random().toString(16).slice(2)}`
  const response = await apiClient.post<KnowledgeMaterialReceipt>('/api/v1/admin/knowledge-materials', form, {
    headers: { 'Idempotency-Key': idempotencyKey },
  })
  return response.data
}

export async function reviewKnowledgeMaterial(
  materialId: string,
  payload: { revision: number; decision: 'APPROVE_FOR_ANALYSIS' | 'REJECT'; reviewed_by: string; review_note: string },
): Promise<KnowledgeMaterial> {
  const response = await apiClient.post<KnowledgeMaterial>(
    `/api/v1/admin/knowledge-materials/${encodeURIComponent(materialId)}/review`, payload,
  )
  return response.data
}

export async function listKnowledgeQualityAssessments(): Promise<KnowledgeQualityAssessmentList> {
  const response = await apiClient.get<KnowledgeQualityAssessmentList>('/api/v1/admin/knowledge-quality/assessments')
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

function modulesFromAiSuccessEnvelope(payload: unknown): unknown[] {
  if (typeof payload !== 'object' || payload === null) return []
  const envelope = payload as { success?: unknown; data?: unknown }
  if (envelope.success !== true || typeof envelope.data !== 'object' || envelope.data === null) return []

  const data = envelope.data as { modules?: unknown }
  return Array.isArray(data.modules) ? data.modules : []
}

/**
 * The sole A-line path declared by ai-control.v1. This adapter consumes only
 * the A success envelope's `data.modules` field and never fabricates modules.
 */
export async function listAiModules(): Promise<AiModule[]> {
  const response = await aiClient.get<unknown>('/api/admin/ai/modules')
  return modulesFromAiSuccessEnvelope(response.data).map(normalizeAiModule)
}

/**
 * Read-only A-line control-centre projection frozen by ai-control.v1.1.
 *
 * Every nullable field deliberately means "the provider did not make this
 * fact available".  The Admin UI must never turn it into a fabricated zero,
 * a demo number, or a successful service state.
 */
export interface AiControlCenterOverview {
  moduleId: string
  service: {
    status: string | null
    ready: boolean | null
    modelConfigured: boolean | null
    initializationError: string | null
  }
  model: {
    provider: string | null
    name: string | null
    configured: boolean | null
  }
  knowledge: {
    status: string | null
    queryableChunkCount: number | null
    scope: string | null
  }
  runtime: {
    metricsScope: string | null
    callCount: number | null
    successCount: number | null
    errorCount: number | null
    averageLatencyMs: number | null
    lastCalledAt: string | null
    lastErrorSummary: string | null
  }
  latestEvaluation: {
    status: string | null
    evaluation: {
      executedAt: string | null
      datasetVersion: string | null
      totalCases: number | null
      passedCases: number | null
      passRate: number | null
    } | null
  }
  technical: {
    promptVersion: string | null
    promptHash: string | null
  }
}

type UnknownRecord = Record<string, unknown>

function recordOrEmpty(value: unknown): UnknownRecord {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
    ? value as UnknownRecord
    : {}
}

function nullableString(value: unknown): string | null {
  return typeof value === 'string' ? value : null
}

function nullableBoolean(value: unknown): boolean | null {
  return typeof value === 'boolean' ? value : null
}

function nullableNumber(value: unknown): number | null {
  return typeof value === 'number' && Number.isFinite(value) ? value : null
}

/** Extract only the `data` object promised by A's success envelope. */
export function aiControlOverviewFromSuccessEnvelope(payload: unknown): AiControlCenterOverview {
  const envelope = recordOrEmpty(payload)
  if (envelope.success !== true) {
    throw new Error('AI 控制中心未返回成功结果。')
  }

  const data = recordOrEmpty(envelope.data)
  const moduleId = nullableString(data.module_id)
  if (!moduleId) {
    throw new Error('AI 控制中心返回的数据不符合已冻结接口。')
  }

  const service = recordOrEmpty(data.service)
  const model = recordOrEmpty(data.model)
  const knowledge = recordOrEmpty(data.knowledge)
  const runtime = recordOrEmpty(data.runtime)
  const latestEvaluation = recordOrEmpty(data.latest_evaluation)
  const evaluation = recordOrEmpty(latestEvaluation.evaluation)
  const technical = recordOrEmpty(data.technical)

  return {
    moduleId,
    service: {
      status: nullableString(service.status),
      ready: nullableBoolean(service.ready),
      modelConfigured: nullableBoolean(service.model_configured),
      initializationError: nullableString(service.initialization_error),
    },
    model: {
      provider: nullableString(model.provider),
      name: nullableString(model.name),
      configured: nullableBoolean(model.configured),
    },
    knowledge: {
      status: nullableString(knowledge.status),
      queryableChunkCount: nullableNumber(knowledge.queryable_chunk_count),
      scope: nullableString(knowledge.scope),
    },
    runtime: {
      metricsScope: nullableString(runtime.metrics_scope),
      callCount: nullableNumber(runtime.call_count),
      successCount: nullableNumber(runtime.success_count),
      errorCount: nullableNumber(runtime.error_count),
      averageLatencyMs: nullableNumber(runtime.average_latency_ms),
      lastCalledAt: nullableString(runtime.last_called_at),
      lastErrorSummary: nullableString(runtime.last_error_summary),
    },
    latestEvaluation: {
      status: nullableString(latestEvaluation.status),
      evaluation: Object.keys(evaluation).length === 0 ? null : {
        executedAt: nullableString(evaluation.executed_at),
        datasetVersion: nullableString(evaluation.dataset_version),
        totalCases: nullableNumber(evaluation.total_cases),
        passedCases: nullableNumber(evaluation.passed_cases),
        passRate: nullableNumber(evaluation.pass_rate),
      },
    },
    technical: {
      promptVersion: nullableString(technical.prompt_version),
      promptHash: nullableString(technical.prompt_hash),
    },
  }
}

/** The only AI-control overview request used by the operator-facing screen. */
export async function getAiControlCenterOverview(): Promise<AiControlCenterOverview> {
  const response = await aiClient.get<unknown>('/api/admin/ai/control-center/overview')
  return aiControlOverviewFromSuccessEnvelope(response.data)
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
