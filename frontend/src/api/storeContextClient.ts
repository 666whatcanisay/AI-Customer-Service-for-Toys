import { createAuthenticatedHttp } from './authenticatedHttp'
import { toPlatformClientError } from './errorMapper'
import { adaptContextResolution, adaptWorkspaceContext } from './storeContextAdapter'
import type { ContextResolution, ContextResolutionRequest, WorkspaceContext } from './storeContextTypes'

const configuredBaseUrl = (import.meta.env.VITE_PLATFORM_API_BASE_URL || '/platform-api')
  .trim().replace(/\/$/, '')
const http = createAuthenticatedHttp({ baseURL: configuredBaseUrl, timeout: 15_000 })

export const storeContextClient = {
  async getContext(signal?: AbortSignal): Promise<WorkspaceContext> {
    try {
      return adaptWorkspaceContext((await http.get('/api/v1/workspace/context', { signal })).data)
    } catch (error) { throw toPlatformClientError(error) }
  },
  async resolve(request: ContextResolutionRequest, signal?: AbortSignal): Promise<ContextResolution> {
    try {
      const response = await http.post('/api/v1/workspace/context-resolutions', {
        conversation: request.conversation,
        store_id: request.storeId ?? null,
        confirmed_product_id: request.confirmedProductId ?? null,
        confirmed_sku_id: request.confirmedSkuId ?? null
      }, { signal })
      return adaptContextResolution(response.data)
    } catch (error) { throw toPlatformClientError(error) }
  }
}
