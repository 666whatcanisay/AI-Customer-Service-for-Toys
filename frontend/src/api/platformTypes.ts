export interface PlatformHealth {
  status: string
  service: string | null
}

export type CatalogResultStatus = 'COMPLETE' | 'PARTIAL'

export interface CatalogWarning {
  code: string
  entityType: 'STORE' | 'PRODUCT' | 'SKU'
  count: number
  message: string
}

export interface CatalogEnvelope<T> {
  schemaVersion: 'pilot-business-catalog.v1.1'
  resultStatus: CatalogResultStatus
  items: T[]
  total: number
  warnings: CatalogWarning[]
}

export interface CatalogStore {
  tenantId: string
  platform: string
  storeCode: string
  name: string
  dataSource: 'TEST' | 'INITIAL_IMPORT' | 'PILOT'
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
  dataSource: 'TEST' | 'INITIAL_IMPORT' | 'PILOT'
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
  dataSource: 'TEST' | 'INITIAL_IMPORT' | 'PILOT'
  customerServiceStatus: 'ENABLED'
}

export interface PlatformCatalogClient {
  getHealth(signal?: AbortSignal): Promise<PlatformHealth>
  listStores(signal?: AbortSignal): Promise<CatalogEnvelope<CatalogStore>>
  listProducts(
    store: CatalogStore,
    signal?: AbortSignal
  ): Promise<CatalogEnvelope<CatalogProduct>>
  listSkus(
    store: CatalogStore,
    product: CatalogProduct,
    signal?: AbortSignal
  ): Promise<CatalogEnvelope<CatalogSku>>
}
