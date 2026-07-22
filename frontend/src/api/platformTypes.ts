export interface PlatformHealth {
  status: string
  service: string | null
}

export interface CatalogStore {
  tenantId: string
  platform: string
  storeCode: string
  name: string
  trialEnabled: boolean
  knowledgeScope: string
  responseMode: string
  allowAutoSend: boolean
  testDataMode: boolean
  productionUsable: boolean
}

export interface CatalogProduct {
  productId: string
  platform: string
  storeCode: string
  officialName: string
  displayName: string
  salesStatus: string
  ageMin: number | null
  ageMax: number | null
  safetySummary: string | null
  reviewStatus: string
  publishable: boolean
}

export interface CatalogSku {
  skuId: string
  productId: string
  skuCode: string
  officialName: string
  displayName: string
  relationType: string
  canonicalSkuId: string | null
  referenceSkuId: string | null
  componentSkuRefs: string[]
  publishable: boolean
}

export interface PlatformCatalogClient {
  getHealth(signal?: AbortSignal): Promise<PlatformHealth>
  listStores(signal?: AbortSignal): Promise<CatalogStore[]>
  listProducts(store: CatalogStore, signal?: AbortSignal): Promise<CatalogProduct[]>
  listSkus(
    store: CatalogStore,
    product: CatalogProduct,
    signal?: AbortSignal
  ): Promise<CatalogSku[]>
}
