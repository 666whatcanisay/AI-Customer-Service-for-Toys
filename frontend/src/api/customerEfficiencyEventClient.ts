import axios from 'axios'
import {
  adaptCustomerEfficiencyEventReceipt,
  toCustomerEfficiencyEventPayload
} from './customerEfficiencyEventAdapter'
import { toCustomerEfficiencyEventClientError } from './errorMapper'
import { PlatformAdapterError } from './platformAdapter'
import type {
  CustomerEfficiencyEventApiClient,
  CustomerEfficiencyEventDraft
} from './customerEfficiencyEventTypes'

const configuredBaseUrl = (import.meta.env.VITE_PLATFORM_API_BASE_URL || '/platform-api')
  .trim()
  .replace(/\/$/, '')

const http = axios.create({
  baseURL: configuredBaseUrl,
  timeout: 3_000,
  headers: {
    Accept: 'application/json',
    'Content-Type': 'application/json'
  }
})

const endpoint = '/api/v1/customer-efficiency/events'

export const createCustomerEfficiencyOpaqueId = (prefix: 'cee' | 'conv' | 'int' | 'op'): string => {
  const randomPart =
    typeof globalThis.crypto?.randomUUID === 'function'
      ? globalThis.crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`

  return `${prefix}-${randomPart}`
}

export const customerEfficiencyEventClient: CustomerEfficiencyEventApiClient = {
  async submit(draft, idempotencyKey) {
    try {
      const normalizedIdempotencyKey = idempotencyKey.trim()
      if (!normalizedIdempotencyKey) {
        throw new PlatformAdapterError('客服效率事件请求缺少 Idempotency-Key')
      }
      const response = await http.post(
        endpoint,
        toCustomerEfficiencyEventPayload(draft),
        { headers: { 'Idempotency-Key': normalizedIdempotencyKey } }
      )
      return adaptCustomerEfficiencyEventReceipt(response.data, draft.eventType)
    } catch (error) {
      throw toCustomerEfficiencyEventClientError(error)
    }
  }
}
