import { createAuthenticatedHttp } from './authenticatedHttp'
import { adaptCustomerKnowledgeStatus } from './customerKnowledgeStatusAdapter'
import { toCustomerKnowledgeStatusClientError } from './errorMapper'
import type {
  CustomerKnowledgeStatusClient,
  CustomerKnowledgeStatusScope
} from './customerKnowledgeStatusTypes'

// A supplied URL keeps the explicit direct-debug mode. Normal Vite starts use
// the same-origin proxy, so customer browsers only connect to port 5173.
const configuredBaseUrl = (import.meta.env.VITE_PLATFORM_API_BASE_URL || '/platform-api')
  .trim()
  .replace(/\/$/, '')

const http = createAuthenticatedHttp({
  baseURL: configuredBaseUrl,
  timeout: 15_000,
  headers: {
    Accept: 'application/json'
  }
})

export const customerKnowledgeStatusClient: CustomerKnowledgeStatusClient = {
  async getStatus(scope, signal) {
    try {
      const response = await http.get(
        `/api/v1/customer-service/catalog/products/${encodeURIComponent(scope.productId)}/ai-knowledge`,
        { signal }
      )
      return adaptCustomerKnowledgeStatus(response.data)
    } catch (error) {
      throw toCustomerKnowledgeStatusClientError(error)
    }
  }
}
