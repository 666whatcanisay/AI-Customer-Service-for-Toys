import axios from 'axios'

import { adaptCustomerIdentity, adaptCustomerIdentityList, CustomerIdentityAdapterError } from './customerIdentityAdapter'
import type { CustomerIdentityClient } from './customerIdentityTypes'

const configuredBaseUrl = (import.meta.env.VITE_PLATFORM_API_BASE_URL || '/platform-api')
  .trim()
  .replace(/\/$/, '')

const http = axios.create({
  baseURL: configuredBaseUrl,
  timeout: 15_000,
  headers: { Accept: 'application/json' },
})

export type CustomerIdentityErrorCode =
  | 'CUSTOMER_USER_NOT_FOUND'
  | 'CUSTOMER_USER_DISABLED'
  | 'CUSTOMER_USER_STORE_FORBIDDEN'
  | null

export class CustomerIdentityClientError extends Error {
  constructor(
    public readonly kind: 'unavailable' | 'contract' | 'invalid-selection' | 'unknown',
    message: string,
    public readonly code: CustomerIdentityErrorCode = null,
  ) {
    super(message)
    this.name = 'CustomerIdentityClientError'
  }
}

const errorCode = (data: unknown): CustomerIdentityErrorCode => {
  if (!data || typeof data !== 'object') return null
  const error = (data as { error?: unknown }).error
  if (!error || typeof error !== 'object') return null
  const code = (error as { code?: unknown }).code
  return code === 'CUSTOMER_USER_NOT_FOUND' || code === 'CUSTOMER_USER_DISABLED' || code === 'CUSTOMER_USER_STORE_FORBIDDEN'
    ? code
    : null
}

const mapError = (error: unknown): CustomerIdentityClientError => {
  if (error instanceof CustomerIdentityClientError) return error
  if (error instanceof CustomerIdentityAdapterError) return new CustomerIdentityClientError('contract', error.message)
  if (axios.isAxiosError(error)) {
    const code = errorCode(error.response?.data)
    const message = typeof error.response?.data?.error?.message === 'string'
      ? error.response.data.error.message
      : error.message
    if (code) return new CustomerIdentityClientError('invalid-selection', '所选客服身份已失效，请重新选择。', code)
    if (error.code === 'ECONNABORTED' || error.code === 'ERR_NETWORK' || (error.response?.status ?? 0) >= 500) {
      return new CustomerIdentityClientError('unavailable', '客服身份服务暂时不可用，请稍后重试。')
    }
    return new CustomerIdentityClientError('unknown', message || '无法读取客服身份。')
  }
  return new CustomerIdentityClientError('unknown', error instanceof Error ? error.message : '无法读取客服身份。')
}

export const customerIdentityClient: CustomerIdentityClient = {
  async list(signal) {
    try {
      const response = await http.get('/api/v1/customer-identities', { signal })
      return adaptCustomerIdentityList(response.data)
    } catch (error) {
      throw mapError(error)
    }
  },
  async get(userId, signal) {
    try {
      const normalized = userId.trim()
      if (!normalized) throw new CustomerIdentityClientError('invalid-selection', '客服身份不能为空。')
      const response = await http.get(`/api/v1/customer-identities/${encodeURIComponent(normalized)}`, { signal })
      const identity = adaptCustomerIdentity(response.data)
      if (identity.status !== 'ACTIVE') {
        throw new CustomerIdentityClientError('invalid-selection', '所选客服身份已停用，请重新选择。', 'CUSTOMER_USER_DISABLED')
      }
      return identity
    } catch (error) {
      throw mapError(error)
    }
  },
}
