import axios from 'axios'

import { adaptCustomerEfficiencyReceipt, CustomerEfficiencyAdapterError, toCustomerEfficiencyPayload } from './customerEfficiencyAdapter'
import type { CustomerEfficiencyClient } from './customerEfficiencyTypes'

const configuredBaseUrl = (import.meta.env.VITE_PLATFORM_API_BASE_URL || '/platform-api')
  .trim()
  .replace(/\/$/, '')

const http = axios.create({
  baseURL: configuredBaseUrl,
  timeout: 15_000,
  headers: { Accept: 'application/json', 'Content-Type': 'application/json' },
})

export class CustomerEfficiencyClientError extends Error {
  constructor(message: string, public readonly code: string | null = null) {
    super(message)
    this.name = 'CustomerEfficiencyClientError'
  }
}

export const createCustomerEfficiencyIdempotencyKey = (): string => {
  const suffix = typeof globalThis.crypto?.randomUUID === 'function'
    ? globalThis.crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  return `customer-efficiency-${suffix}`
}

export const createCustomerInteractionId = (): string => {
  const suffix = typeof globalThis.crypto?.randomUUID === 'function'
    ? globalThis.crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  return `interaction-${suffix}`
}

export const customerEfficiencyClient: CustomerEfficiencyClient = {
  async submit(draft, idempotencyKey, signal) {
    try {
      const key = idempotencyKey.trim()
      if (!key) throw new CustomerEfficiencyAdapterError('效率事件请求缺少 Idempotency-Key。')
      const response = await http.post('/api/v1/customer-efficiency/events', toCustomerEfficiencyPayload(draft), {
        signal,
        headers: { 'Idempotency-Key': key },
      })
      return adaptCustomerEfficiencyReceipt(response.data)
    } catch (error) {
      if (error instanceof CustomerEfficiencyAdapterError) throw error
      if (axios.isAxiosError(error)) {
        const detail = error.response?.data?.error?.message
        const rawCode = error.response?.data?.error?.code
        const code = typeof rawCode === 'string' ? rawCode : null
        throw new CustomerEfficiencyClientError(
          typeof detail === 'string' ? detail : '效率事件暂时未能记录，不影响当前 AI 建议。',
          code,
        )
      }
      throw new CustomerEfficiencyClientError(
        error instanceof Error ? error.message : '效率事件暂时未能记录，不影响当前 AI 建议。',
      )
    }
  },
}
