import axios from 'axios'
import { adaptExperienceCaseReceipt, toExperienceCasePayload } from './experienceCaseAdapter'
import { toPlatformClientError } from './errorMapper'
import type { ExperienceCaseApiClient } from './experienceCaseTypes'

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

const endpoint = '/api/v1/customer-experience-cases'

// C has not yet published the final experience-case contract. This client has
// no production fallback: only an actual response with a recognized status is accepted.
export const experienceCaseClient: ExperienceCaseApiClient = {
  async submit(draft, signal) {
    try {
      const response = await http.post(endpoint, toExperienceCasePayload(draft), { signal })
      return adaptExperienceCaseReceipt(response.data)
    } catch (error) {
      throw toPlatformClientError(error)
    }
  }
}
