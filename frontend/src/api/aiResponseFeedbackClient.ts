import axios from 'axios'
import { adaptAiResponseFeedbackReceipt, toAiResponseFeedbackPayload } from './aiResponseFeedbackAdapter'
import { toAiResponseFeedbackClientError } from './errorMapper'
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

// No local success or experience-case fallback is allowed for AI problem feedback.
export const aiResponseFeedbackClient: AiResponseFeedbackApiClient = {
  async submit(draft, signal) {
    try {
      const response = await http.post(endpoint, toAiResponseFeedbackPayload(draft), { signal })
      return adaptAiResponseFeedbackReceipt(response.data)
    } catch (error) {
      throw toAiResponseFeedbackClientError(error)
    }
  }
}
