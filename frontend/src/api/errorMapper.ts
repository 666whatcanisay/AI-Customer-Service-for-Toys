import axios from 'axios'
import { RagAdapterError } from './ragAdapter'
import { PlatformAdapterError } from './platformAdapter'

export type RagErrorKind =
  | 'canceled'
  | 'timeout'
  | 'invalid_request'
  | 'risk_review'
  | 'unavailable'
  | 'contract'
  | 'unknown'

export class RagClientError extends Error {
  constructor(
    public readonly kind: RagErrorKind,
    message: string,
    public readonly status: number | null = null
  ) {
    super(message)
    this.name = 'RagClientError'
  }
}

export type PlatformErrorKind = 'canceled' | 'timeout' | 'unavailable' | 'contract' | 'unknown'

export class PlatformClientError extends Error {
  constructor(
    public readonly kind: PlatformErrorKind,
    message: string,
    public readonly status: number | null = null
  ) {
    super(message)
    this.name = 'PlatformClientError'
  }
}

const recordValue = (value: unknown): Record<string, unknown> | null =>
  typeof value === 'object' && value !== null ? (value as Record<string, unknown>) : null

const responseMessage = (value: unknown): string | null => {
  const data = recordValue(value)
  if (!data) return null
  const error = recordValue(data.error)
  if (error && typeof error.message === 'string' && error.message) return error.message
  for (const key of ['message', 'detail']) {
    const item = data[key]
    if (typeof item === 'string' && item) return item
  }
  return null
}

const responseCode = (value: unknown): string | null => {
  const data = recordValue(value)
  if (!data) return null
  const error = recordValue(data.error)
  if (error && typeof error.code === 'string') return error.code
  for (const key of ['code', 'error_code']) {
    const item = data[key]
    if (typeof item === 'string') return item
  }
  return null
}

export const toRagClientError = (error: unknown): RagClientError => {
  if (error instanceof RagClientError) return error
  if (error instanceof RagAdapterError) return new RagClientError('contract', error.message)
  if (axios.isCancel(error)) return new RagClientError('canceled', '请求已取消，可重新提交')

  if (axios.isAxiosError(error)) {
    const status = error.response?.status ?? null
    const code = responseCode(error.response?.data)
    const detail = responseMessage(error.response?.data)

    if (error.code === 'ECONNABORTED') {
      return new RagClientError('timeout', '请求超时，请确认 RAG 服务状态后重试', status)
    }
    if (code === 'INVALID_REQUEST' || status === 422) {
      return new RagClientError('invalid_request', detail ?? '请求参数不符合 RAG API 要求', status)
    }
    if (code === 'RISK_REVIEW_REQUIRED') {
      return new RagClientError('risk_review', detail ?? '该回答需要人工风险复核', status)
    }
    if (status === 503 || status === 500 || error.code === 'ERR_NETWORK') {
      return new RagClientError('unavailable', detail ?? 'RAG API 当前不可用，请稍后重试', status)
    }
    return new RagClientError('unknown', detail ?? error.message ?? 'RAG API 请求失败', status)
  }

  return new RagClientError('unknown', error instanceof Error ? error.message : '未知错误')
}

export const toPlatformClientError = (error: unknown): PlatformClientError => {
  if (error instanceof PlatformClientError) return error
  if (error instanceof PlatformAdapterError) {
    return new PlatformClientError('contract', error.message)
  }
  if (axios.isCancel(error)) {
    return new PlatformClientError('canceled', '目录请求已取消')
  }

  if (axios.isAxiosError(error)) {
    const status = error.response?.status ?? null
    const detail = responseMessage(error.response?.data)
    if (error.code === 'ECONNABORTED') {
      return new PlatformClientError('timeout', 'C 目录服务请求超时，请稍后重试', status)
    }
    if (status === 503 || status === 500 || error.code === 'ERR_NETWORK') {
      return new PlatformClientError(
        'unavailable',
        detail ?? 'C 目录服务当前不可用，请联系中台维护人员',
        status
      )
    }
    return new PlatformClientError(
      'unknown',
      detail ?? error.message ?? 'C 目录服务请求失败',
      status
    )
  }

  return new PlatformClientError(
    'unknown',
    error instanceof Error ? error.message : 'C 目录服务发生未知错误'
  )
}
