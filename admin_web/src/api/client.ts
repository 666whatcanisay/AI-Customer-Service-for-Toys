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

export interface Page<T> {
  items: T[]
  page: number
  page_size: number
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
