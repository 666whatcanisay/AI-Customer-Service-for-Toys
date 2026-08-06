import { createAuthenticatedHttp } from './authenticatedHttp'

import {
  adaptAiInteractionEventReceipt,
  toAiInteractionEventPayload
} from './aiInteractionEventAdapter'
import { toAiResponseFeedbackClientError } from './errorMapper'
import { PlatformAdapterError } from './platformAdapter'
import type { AiInteractionEventApiClient } from './aiInteractionEventTypes'

const configuredBaseUrl = (import.meta.env.VITE_PLATFORM_API_BASE_URL || '/platform-api')
  .trim()
  .replace(/\/$/, '')

const http = createAuthenticatedHttp({
  baseURL: configuredBaseUrl,
  timeout: 15_000,
  headers: {
    Accept: 'application/json',
    'Content-Type': 'application/json'
  }
})

export const createAiInteractionEventIdempotencyKey = (): string => {
  const randomPart =
    typeof globalThis.crypto?.randomUUID === 'function'
      ? globalThis.crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  return `ai-interaction-${randomPart}`
}

export const createLocalInteractionId = (): string => {
  const randomPart =
    typeof globalThis.crypto?.randomUUID === 'function'
      ? globalThis.crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  return `interaction-${randomPart}`
}

export const aiInteractionEventClient: AiInteractionEventApiClient = {
  async submit(draft, idempotencyKey, signal) {
    try {
      const key = idempotencyKey.trim()
      if (!key) throw new PlatformAdapterError('AI 行为事件缺少 Idempotency-Key')
      const response = await http.post(
        '/api/v1/ai-interaction-events',
        toAiInteractionEventPayload(draft),
        { signal, headers: { 'Idempotency-Key': key } }
      )
      return adaptAiInteractionEventReceipt(response.data)
    } catch (error) {
      throw toAiResponseFeedbackClientError(error)
    }
  }
}
