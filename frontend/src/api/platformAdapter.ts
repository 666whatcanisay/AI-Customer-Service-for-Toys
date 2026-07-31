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

const requiredEnum = <T extends string>(
  record: UnknownRecord,
  key: string,
  entity: string,
  values: readonly T[]
): T => {
  const value = requiredString(record, key, entity)
  if (!values.includes(value as T)) {
    throw new PlatformAdapterError(`C ${entity}记录字段 ${key} 不符合冻结契约`)
  }
  return value as T
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
    payload.schema_version !== 'pilot-business-catalog.v1.1' ||
    !['COMPLETE', 'PARTIAL'].includes(String(payload.result_status)) ||
    !Array.isArray(payload.items) ||
    typeof payload.total !== 'number' ||
    !Number.isInteger(payload.total) ||
    payload.total < 0 ||
    !Array.isArray(payload.warnings)
  ) {
    throw new PlatformAdapterError(
      `C ${entity}接口必须返回 pilot-business-catalog.v1.1 envelope`
    )
  }
  return payload.items.map((value) => {
    if (!isRecord(value)) throw new PlatformAdapterError(`C ${entity}列表包含无效记录`)
    return value
  })
}

/**
 * Isolate a technically malformed item without inferring that it is enabled.
 * C remains the sole availability owner; B only consumes records that satisfy
 * the frozen final-projection schema. If every returned record is malformed,
 * surface a contract error instead of presenting an authoritative empty list.
 */
const adaptProjectedItems = <T>(
  payload: unknown,
  entity: string,
  mapper: (record: UnknownRecord) => T
): T[] => {
  const records = listEnvelope(payload, entity)
  const items: T[] = []
  let firstError: PlatformAdapterError | null = null
  for (const record of records) {
    try {
      items.push(mapper(record))
    } catch (error) {
      if (!(error instanceof PlatformAdapterError)) throw error
      if (firstError === null) firstError = error
    }
  }
  if (records.length > 0 && items.length === 0 && firstError) throw firstError
  return items
}

export const adaptPlatformHealth = (payload: unknown): PlatformHealth => {
  if (!isRecord(payload)) throw new PlatformAdapterError('C 健康检查返回了无法识别的数据格式')
  return {
    status: requiredString(payload, 'status', '健康检查'),
    service: optionalString(payload, 'service')
  }
}

export const adaptStoresResponse = (payload: unknown): CatalogStore[] =>
  adaptProjectedItems(payload, '店铺', (value) => {
    const allowAutoSend = requiredBoolean(value, 'allow_auto_send', '店铺')
    if (allowAutoSend) throw new PlatformAdapterError('C 店铺记录违反禁止自动发送契约')
    return {
      tenantId: requiredString(value, 'tenant_id', '店铺'),
      platform: requiredString(value, 'platform', '店铺'),
      storeCode: requiredString(value, 'store_code', '店铺'),
      name: requiredString(value, 'store_name', '店铺'),
      dataSource: requiredEnum(value, 'data_source', '店铺', ['TEST', 'INITIAL_IMPORT', 'PILOT'] as const),
      customerServiceStatus: requiredEnum(
        value,
        'customer_service_status',
        '店铺',
        ['ENABLED'] as const
      ),
      allowAutoSend
    }
  })

export const adaptProductsResponse = (payload: unknown): CatalogProduct[] =>
  adaptProjectedItems(payload, '商品', (value) => ({
    productId: requiredString(value, 'product_id', '商品'),
    platform: requiredString(value, 'platform', '商品'),
    storeCode: requiredString(value, 'store_code', '商品'),
    officialName: requiredString(value, 'product_name_official', '商品'),
    displayName: requiredString(value, 'product_name_display', '商品'),
    salesStatus: requiredString(value, 'sales_status', '商品'),
    ageMin: optionalNumber(value, 'age_min'),
    ageMax: optionalNumber(value, 'age_max'),
    safetySummary: optionalString(value, 'safety_summary'),
    knowledgeStatus: requiredString(value, 'knowledge_status', '商品'),
    dataSource: requiredEnum(value, 'data_source', '商品', ['TEST', 'INITIAL_IMPORT', 'PILOT'] as const),
    customerServiceStatus: requiredEnum(
      value,
      'customer_service_status',
      '商品',
      ['ENABLED'] as const
    )
  }))

export const adaptSkusResponse = (payload: unknown): CatalogSku[] =>
  adaptProjectedItems(payload, 'SKU', (value) => ({
    skuId: requiredString(value, 'sku_id', 'SKU'),
    productId: requiredString(value, 'product_id', 'SKU'),
    skuCode: requiredString(value, 'sku_code', 'SKU'),
    officialName: requiredString(value, 'sku_name_official', 'SKU'),
    displayName: requiredString(value, 'sku_name_display', 'SKU'),
    relationType: requiredString(value, 'relation_type', 'SKU'),
    canonicalSkuId: optionalString(value, 'canonical_sku_id'),
    referenceSkuId: optionalString(value, 'reference_sku_id'),
    componentSkuRefs: stringList(value, 'component_sku_refs'),
    dataSource: requiredEnum(value, 'data_source', 'SKU', ['TEST', 'INITIAL_IMPORT', 'PILOT'] as const),
    customerServiceStatus: requiredEnum(
      value,
      'customer_service_status',
      'SKU',
      ['ENABLED'] as const
    )
  }))
