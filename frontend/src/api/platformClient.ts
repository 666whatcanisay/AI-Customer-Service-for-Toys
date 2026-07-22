import axios from 'axios'
import {
  adaptPlatformHealth,
  adaptProductsResponse,
  adaptSkusResponse,
  adaptStoresResponse
} from './platformAdapter'
import { toPlatformClientError } from './errorMapper'
import type { PlatformCatalogClient } from './platformTypes'

const configuredBaseUrl = (import.meta.env.VITE_PLATFORM_API_BASE_URL || 'http://127.0.0.1:8012')
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
      const response = await http.get('/api/v1/stores', { signal })
      return adaptStoresResponse(response.data)
    } catch (error) {
      throw toPlatformClientError(error)
    }
  },

  async listProducts(store, signal) {
    try {
      const response = await http.get(
        `/api/v1/stores/${encodeURIComponent(store.storeCode)}/products`,
        {
          signal,
          params: {
            tenant_id: store.tenantId,
            platform: store.platform
          }
        }
      )
      return adaptProductsResponse(response.data)
    } catch (error) {
      throw toPlatformClientError(error)
    }
  },

  async listSkus(store, product, signal) {
    try {
      const response = await http.get(
        `/api/v1/products/${encodeURIComponent(product.productId)}/skus`,
        {
          signal,
          params: {
            tenant_id: store.tenantId,
            platform: store.platform,
            store_code: store.storeCode
          }
        }
      )
      return adaptSkusResponse(response.data)
    } catch (error) {
      throw toPlatformClientError(error)
    }
  }
}
