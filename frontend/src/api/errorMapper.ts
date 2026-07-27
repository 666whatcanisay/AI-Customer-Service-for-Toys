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

export type AiResponseFeedbackErrorKind =
  | 'canceled'
  | 'timeout'
  | 'validation'
  | 'unavailable'
  | 'contract'
  | 'unknown'

export class AiResponseFeedbackClientError extends Error {
  constructor(
    public readonly kind: AiResponseFeedbackErrorKind,
    message: string,
    public readonly status: number | null = null
  ) {
    super(message)
    this.name = 'AiResponseFeedbackClientError'
  }
}

export type CustomerEfficiencyEventErrorKind =
  | 'canceled'
  | 'timeout'
  | 'schema_version'
  | 'forbidden'
  | 'idempotency_conflict'
  | 'event_sequence'
  | 'validation'
  | 'feedback_reference'
  | 'rate_limited'
  | 'unavailable'
  | 'contract'
  | 'unknown'

export class CustomerEfficiencyEventClientError extends Error {
  constructor(
    public readonly kind: CustomerEfficiencyEventErrorKind,
    message: string,
    public readonly status: number | null = null
  ) {
    super(message)
    this.name = 'CustomerEfficiencyEventClientError'
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

export const toAiResponseFeedbackClientError = (error: unknown): AiResponseFeedbackClientError => {
  if (error instanceof AiResponseFeedbackClientError) return error
  if (error instanceof PlatformAdapterError) {
    return new AiResponseFeedbackClientError('contract', error.message)
  }
  if (axios.isCancel(error)) {
    return new AiResponseFeedbackClientError('canceled', 'AI 问题反馈已取消')
  }

  if (axios.isAxiosError(error)) {
    const status = error.response?.status ?? null
    const code = responseCode(error.response?.data)
    const detail = responseMessage(error.response?.data)
    if (error.code === 'ECONNABORTED') {
      return new AiResponseFeedbackClientError('timeout', 'AI 问题反馈请求超时，请稍后重试', status)
    }
    if (code === 'AI_RESPONSE_FEEDBACK_VALIDATION_FAILED' || status === 422) {
      return new AiResponseFeedbackClientError(
        'validation',
        detail ?? 'AI 问题反馈不符合冻结接口要求',
        status
      )
    }
    if (status === 503 || status === 500 || error.code === 'ERR_NETWORK') {
      return new AiResponseFeedbackClientError(
        'unavailable',
        detail ?? 'AI 问题反馈服务当前不可用，请稍后重试',
        status
      )
    }
    return new AiResponseFeedbackClientError(
      'unknown',
      detail ?? error.message ?? 'AI 问题反馈请求失败',
      status
    )
  }

  return new AiResponseFeedbackClientError(
    'unknown',
    error instanceof Error ? error.message : 'AI 问题反馈服务发生未知错误'
  )
}

export const toCustomerEfficiencyEventClientError = (
  error: unknown
): CustomerEfficiencyEventClientError => {
  if (error instanceof CustomerEfficiencyEventClientError) return error
  if (error instanceof PlatformAdapterError) {
    return new CustomerEfficiencyEventClientError('contract', error.message)
  }
  if (axios.isCancel(error)) {
    return new CustomerEfficiencyEventClientError('canceled', 'Efficiency event request canceled')
  }

  if (axios.isAxiosError(error)) {
    const status = error.response?.status ?? null
    const code = responseCode(error.response?.data)
    const detail = responseMessage(error.response?.data)
    if (error.code === 'ECONNABORTED') {
      return new CustomerEfficiencyEventClientError('timeout', 'Efficiency event request timed out', status)
    }
    if (status === 400 && code === 'CUSTOMER_EFFICIENCY_SCHEMA_VERSION_UNSUPPORTED') {
      return new CustomerEfficiencyEventClientError('schema_version', detail ?? 'Unsupported efficiency event schema version', status)
    }
    if (status === 401 || status === 403) {
      return new CustomerEfficiencyEventClientError('forbidden', detail ?? 'Efficiency event request is not authorized', status)
    }
    if (code === 'CUSTOMER_EFFICIENCY_IDEMPOTENCY_CONFLICT') {
      return new CustomerEfficiencyEventClientError('idempotency_conflict', detail ?? 'Efficiency event idempotency key conflict', status)
    }
    if (code === 'CUSTOMER_EFFICIENCY_EVENT_SEQUENCE_INVALID') {
      return new CustomerEfficiencyEventClientError('event_sequence', detail ?? 'Efficiency event sequence is invalid', status)
    }
    if (code === 'CUSTOMER_EFFICIENCY_EVENT_VALIDATION_FAILED') {
      return new CustomerEfficiencyEventClientError('validation', detail ?? 'Efficiency event validation failed', status)
    }
    if (code === 'CUSTOMER_EFFICIENCY_FEEDBACK_REFERENCE_INVALID') {
      return new CustomerEfficiencyEventClientError('feedback_reference', detail ?? 'Efficiency feedback reference is invalid', status)
    }
    if (status === 429) {
      return new CustomerEfficiencyEventClientError('rate_limited', detail ?? 'Efficiency event rate limit reached', status)
    }
    if (status === 503 || status === 500 || error.code === 'ERR_NETWORK') {
      return new CustomerEfficiencyEventClientError('unavailable', detail ?? 'Efficiency event service is unavailable', status)
    }
    return new CustomerEfficiencyEventClientError(
      'unknown',
      detail ?? error.message ?? 'Efficiency event request failed',
      status
    )
  }

  return new CustomerEfficiencyEventClientError(
    'unknown',
    error instanceof Error ? error.message : 'Unknown efficiency event error'
  )
}
