import axios from 'axios'
import {
  adaptSuggestionList,
  adaptSuggestionReceipt,
  toSuggestionPayload
} from './suggestionAdapter'
import { toPlatformClientError } from './errorMapper'
import type { SuggestionApiClient } from './suggestionTypes'

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

const endpoint = '/api/v1/customer-suggestions'

export const suggestionClient: SuggestionApiClient = {
  async submit(draft, signal) {
    try {
      const response = await http.post(endpoint, toSuggestionPayload(draft), { signal })
      return adaptSuggestionReceipt(response.data)
    } catch (error) {
      throw toPlatformClientError(error)
    }
  },

  async listMine(reporterId, signal) {
    try {
      const response = await http.get(endpoint, {
        signal,
        params: {
          reporter_id: reporterId
        }
      })
      return adaptSuggestionList(response.data, reporterId)
    } catch (error) {
      throw toPlatformClientError(error)
    }
  }
}
