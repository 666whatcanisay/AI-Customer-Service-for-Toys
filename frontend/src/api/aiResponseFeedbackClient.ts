import axios from 'axios'
import { adaptAiResponseFeedbackReceipt, toAiResponseFeedbackPayload } from './aiResponseFeedbackAdapter'
import { toAiResponseFeedbackClientError } from './errorMapper'
import { PlatformAdapterError } from './platformAdapter'
import type { AiResponseFeedbackApiClient } from './aiResponseFeedbackTypes'

const configuredBaseUrl = (import.meta.env.VITE_PLATFORM_API_BASE_URL || '/platform-api')
  .trim()
  .replace(/\/$/, '')

const http = axios.create({
  baseURL: configuredBaseUrl,
  timeout: 15_000,
  headers: {
    Accept: 'application/json',
    'Content-Type': 'application/json'
  }
})

const endpoint = '/api/v1/ai-response-feedback'

export const createAiResponseFeedbackIdempotencyKey = (): string => {
  const randomPart =
    typeof globalThis.crypto?.randomUUID === 'function'
      ? globalThis.crypto.randomUUID()
      : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`

  return `ai-feedback-${randomPart}`
}

// No local success or experience-case fallback is allowed for AI problem feedback.
export const aiResponseFeedbackClient: AiResponseFeedbackApiClient = {
  async submit(draft, idempotencyKey, signal) {
    try {
      const normalizedIdempotencyKey = idempotencyKey.trim()
      if (!normalizedIdempotencyKey) {
        throw new PlatformAdapterError('AI 问题反馈请求缺少 Idempotency-Key')
      }
      const response = await http.post(endpoint, toAiResponseFeedbackPayload(draft), {
        signal,
        headers: { 'Idempotency-Key': normalizedIdempotencyKey }
      })
      return adaptAiResponseFeedbackReceipt(response.data)
    } catch (error) {
      throw toAiResponseFeedbackClientError(error)
    }
  }
}
