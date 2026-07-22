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

export const API_BASE_URL = import.meta.env.VITE_PLATFORM_API_BASE_URL || '/api/platform'

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  timeout: 30000,
})

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
  if (isOfflineError(error)) return '无法连接平台服务，请检查网络或服务状态。'
  if (error instanceof AxiosError) {
    const data = error.response?.data as { error?: { message?: unknown } } | undefined
    const message = data?.error?.message
    if (typeof message === 'string') return message
  }
  return '请求失败，请稍后重试。'
}
