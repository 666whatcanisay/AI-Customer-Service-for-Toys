import type {
  CatalogProduct,
  CatalogSku,
  CatalogStore,
  PlatformHealth
} from './platformTypes'

type UnknownRecord = Record<string, unknown>

export class PlatformAdapterError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'PlatformAdapterError'
  }
}

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const requiredString = (record: UnknownRecord, key: string, entity: string): string => {
  const value = record[key]
  if (typeof value !== 'string' || !value.trim()) {
    throw new PlatformAdapterError(`C ${entity}记录缺少 ${key}`)
  }
  return value.trim()
}

const optionalString = (record: UnknownRecord, key: string): string | null => {
  const value = record[key]
  if (value === null || value === undefined || value === '') return null
  if (typeof value !== 'string') throw new PlatformAdapterError(`C 目录字段 ${key} 类型无效`)
  return value.trim() || null
}

const requiredBoolean = (record: UnknownRecord, key: string, entity: string): boolean => {
  const value = record[key]
  if (typeof value !== 'boolean') {
    throw new PlatformAdapterError(`C ${entity}记录缺少布尔字段 ${key}`)
  }
  return value
}

const optionalNumber = (record: UnknownRecord, key: string): number | null => {
  const value = record[key]
  if (value === null || value === undefined) return null
  if (typeof value !== 'number' || !Number.isFinite(value)) {
    throw new PlatformAdapterError(`C 目录字段 ${key} 类型无效`)
  }
  return value
}

const stringList = (record: UnknownRecord, key: string): string[] => {
  const value = record[key]
  if (!Array.isArray(value) || !value.every((item) => typeof item === 'string')) {
    throw new PlatformAdapterError(`C 目录字段 ${key} 必须为 string[]`)
  }
  return value
}

const listEnvelope = (payload: unknown, entity: string): UnknownRecord[] => {
  if (
    !isRecord(payload) ||
    !Array.isArray(payload.items) ||
    typeof payload.total !== 'number' ||
    !Number.isInteger(payload.total) ||
    payload.total < 0
  ) {
    throw new PlatformAdapterError(`C ${entity}接口必须返回 {items,total}`)
  }
  return payload.items.map((value) => {
    if (!isRecord(value)) throw new PlatformAdapterError(`C ${entity}列表包含无效记录`)
    return value
  })
}

export const adaptPlatformHealth = (payload: unknown): PlatformHealth => {
  if (!isRecord(payload)) throw new PlatformAdapterError('C 健康检查返回了无法识别的数据格式')
  return {
    status: requiredString(payload, 'status', '健康检查'),
    service: optionalString(payload, 'service')
  }
}

export const adaptStoresResponse = (payload: unknown): CatalogStore[] =>
  listEnvelope(payload, '店铺').map((value) => ({
    tenantId: requiredString(value, 'tenant_id', '店铺'),
    platform: requiredString(value, 'platform', '店铺'),
    storeCode: requiredString(value, 'store_code', '店铺'),
    name: requiredString(value, 'store_name', '店铺'),
    trialEnabled: requiredBoolean(value, 'trial_enabled', '店铺'),
    knowledgeScope: requiredString(value, 'knowledge_scope', '店铺'),
    responseMode: requiredString(value, 'response_mode', '店铺'),
    allowAutoSend: requiredBoolean(value, 'allow_auto_send', '店铺'),
    testDataMode: requiredBoolean(value, 'test_data_mode', '店铺'),
    productionUsable: requiredBoolean(value, 'production_usable', '店铺')
  }))

export const adaptProductsResponse = (payload: unknown): CatalogProduct[] =>
  listEnvelope(payload, '商品').map((value) => ({
    productId: requiredString(value, 'product_id', '商品'),
    platform: requiredString(value, 'platform', '商品'),
    storeCode: requiredString(value, 'store_code', '商品'),
    officialName: requiredString(value, 'product_name_official', '商品'),
    displayName: requiredString(value, 'product_name_display', '商品'),
    salesStatus: requiredString(value, 'sales_status', '商品'),
    ageMin: optionalNumber(value, 'age_min'),
    ageMax: optionalNumber(value, 'age_max'),
    safetySummary: optionalString(value, 'safety_summary'),
    reviewStatus: requiredString(value, 'review_status', '商品'),
    publishable: requiredBoolean(value, 'publishable', '商品')
  }))

export const adaptSkusResponse = (payload: unknown): CatalogSku[] =>
  listEnvelope(payload, 'SKU').map((value) => ({
    skuId: requiredString(value, 'sku_id', 'SKU'),
    productId: requiredString(value, 'product_id', 'SKU'),
    skuCode: requiredString(value, 'sku_code', 'SKU'),
    officialName: requiredString(value, 'sku_name_official', 'SKU'),
    displayName: requiredString(value, 'sku_name_display', 'SKU'),
    relationType: requiredString(value, 'relation_type', 'SKU'),
    canonicalSkuId: optionalString(value, 'canonical_sku_id'),
    referenceSkuId: optionalString(value, 'reference_sku_id'),
    componentSkuRefs: stringList(value, 'component_sku_refs'),
    publishable: requiredBoolean(value, 'publishable', 'SKU')
  }))
