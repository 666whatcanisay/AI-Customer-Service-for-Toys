import axios from 'axios'
import {
  adaptPlatformHealth,
  adaptProductsResponse,
  adaptSkusResponse,
  adaptStoresResponse
} from './platformAdapter'
import { toPlatformClientError } from './errorMapper'
import type { PlatformCatalogClient } from './platformTypes'

// A supplied URL keeps the explicit direct-debug mode. Normal Vite starts use
// the same-origin proxy, so a customer browser needs only port 5173.
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

export const platformClient: PlatformCatalogClient = {
  async getHealth(signal) {
    try {
      const response = await http.get('/health', { signal })
      return adaptPlatformHealth(response.data)
    } catch (error) {
      throw toPlatformClientError(error)
    }
  },

  async listStores(signal) {
    try {
      const response = await http.get('/api/v1/customer-service/catalog/stores', { signal })
      return adaptStoresResponse(response.data)
    } catch (error) {
      throw toPlatformClientError(error)
    }
  },

  async listProducts(store, signal) {
    try {
      const response = await http.get('/api/v1/customer-service/catalog/products', {
        signal,
        params: {
          store_code: store.storeCode
        }
      })
      return adaptProductsResponse(response.data)
    } catch (error) {
      throw toPlatformClientError(error)
    }
  },

  async listSkus(_store, product, signal) {
    try {
      const response = await http.get(
        `/api/v1/customer-service/catalog/products/${encodeURIComponent(product.productId)}/skus`,
        { signal }
      )
      return adaptSkusResponse(response.data)
    } catch (error) {
      throw toPlatformClientError(error)
    }
  }
}
