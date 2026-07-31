export interface PlatformHealth {
  status: string
  service: string | null
}

export interface CatalogStore {
  tenantId: string
  platform: string
  storeCode: string
  name: string
  dataSource: 'TEST' | 'PILOT'
  customerServiceStatus: 'ENABLED'
  allowAutoSend: boolean
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
  knowledgeStatus: string
  dataSource: 'TEST' | 'PILOT'
  customerServiceStatus: 'ENABLED'
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
  dataSource: 'TEST' | 'PILOT'
  customerServiceStatus: 'ENABLED'
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
