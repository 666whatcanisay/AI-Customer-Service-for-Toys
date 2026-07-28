import axios from 'axios'
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

const http = axios.create({
  baseURL: configuredBaseUrl,
  timeout: 15_000,
  headers: {
    Accept: 'application/json'
  }
})

const requestParameters = (scope: CustomerKnowledgeStatusScope) => ({
  store_code: scope.storeCode,
  product_id: scope.productId,
  ...(scope.skuId ? { sku_id: scope.skuId } : {})
})

export const customerKnowledgeStatusClient: CustomerKnowledgeStatusClient = {
  async getStatus(scope, signal) {
    try {
      const response = await http.get('/api/v1/customer-knowledge-status', {
        signal,
        params: requestParameters(scope)
      })
      return adaptCustomerKnowledgeStatus(response.data)
    } catch (error) {
      throw toCustomerKnowledgeStatusClientError(error)
    }
  }
}
