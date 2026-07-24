import { beforeEach, describe, expect, it, vi } from 'vitest'

const httpGet = vi.hoisted(() => vi.fn())
const httpCreate = vi.hoisted(() => vi.fn(() => ({ get: httpGet })))

vi.mock('axios', () => ({
  default: {
    create: httpCreate,
    isCancel: () => false,
    isAxiosError: () => false
  }
}))

import { platformClient } from './platformClient'
import type { CatalogProduct, CatalogStore } from './platformTypes'

const store: CatalogStore = {
  tenantId: 'TENANT-PDD-SM-TEST',
  platform: 'pdd',
  storeCode: 'PDD-SM',
  name: '汕明',
  trialEnabled: true,
  knowledgeScope: 'STORE_PRODUCT_SKU',
  responseMode: 'SUGGESTION_ONLY',
  allowAutoSend: false,
  testDataMode: true,
  productionUsable: false
}

const product: CatalogProduct = {
  productId: 'PROD/001',
  platform: 'pdd',
  storeCode: 'PDD-SM',
  officialName: '测试积木',
  displayName: '测试积木套装',
  salesStatus: 'ON_SALE',
  ageMin: 6,
  ageMax: 12,
  safetySummary: '仅用于测试。',
  reviewStatus: 'APPROVED',
  publishable: true
}

describe('platformClient frozen paths', () => {
  beforeEach(() => {
    httpGet.mockReset()
    httpGet.mockResolvedValue({ data: { items: [], total: 0 } })
  })

  it('uses the same-origin platform proxy unless a direct URL is configured', () => {
    expect(httpCreate).toHaveBeenCalledWith(expect.objectContaining({
      baseURL: '/platform-api'
    }))
  })

  it('calls only the three frozen test-catalog routes', async () => {
    await platformClient.listStores()
    await platformClient.listProducts(store)
    await platformClient.listSkus(store, product)

    expect(httpGet.mock.calls).toEqual([
      ['/api/v1/test-catalog/stores', { signal: undefined }],
      [
        '/api/v1/test-catalog/products',
        { signal: undefined, params: { store_code: 'PDD-SM' } }
      ],
      ['/api/v1/test-catalog/products/PROD%2F001/skus', { signal: undefined }]
    ])
  })
})
