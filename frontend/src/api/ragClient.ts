import { createAuthenticatedHttp } from './authenticatedHttp'
import { adaptChatResponse, adaptHealthResponse } from './ragAdapter'
import { toRagClientError } from './errorMapper'
import type { RagApiClient, RagChatRequest } from './ragTypes'

// A supplied URL keeps the explicit direct-debug mode. Normal Vite starts use
// the same-origin proxy, so a customer browser needs only port 5173.
const configuredBaseUrl = (import.meta.env.VITE_PLATFORM_API_BASE_URL || '/platform-api')
  .trim()
  .replace(/\/$/, '')

const http = createAuthenticatedHttp({
  baseURL: configuredBaseUrl,
  timeout: 15_000,
  headers: {
    'Content-Type': 'application/json'
  }
})

export const ragClient: RagApiClient = {
  async getHealth(signal) {
    try {
      const response = await http.get('/api/v1/workspace/ai-health', { signal })
      return adaptHealthResponse(response.data)
    } catch (error) {
      throw toRagClientError(error)
    }
  },

  async chat(request: RagChatRequest, signal) {
    try {
      const response = await http.post('/api/v1/workspace/ai-replies', request, { signal })
      return adaptChatResponse(response.data)
    } catch (error) {
      throw toRagClientError(error)
    }
  }
}
