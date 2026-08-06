import type {
  ContextResolution, ProductContextCandidate, SkuContextCandidate,
  WorkspaceContext, WorkspaceStoreContext
} from './storeContextTypes'

type JsonRecord = Record<string, unknown>
const record = (value: unknown): JsonRecord => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) throw new Error('店铺上下文响应格式无效。')
  return value as JsonRecord
}
const text = (value: unknown): string => {
  if (typeof value !== 'string' || !value) throw new Error('店铺上下文响应缺少文本字段。')
  return value
}
const integer = (value: unknown): number => {
  if (!Number.isInteger(value) || (value as number) < 1) throw new Error('店铺上下文响应缺少标识。')
  return value as number
}
const boolean = (value: unknown): boolean => {
  if (typeof value !== 'boolean') throw new Error('店铺上下文响应缺少布尔字段。')
  return value
}
const array = (value: unknown): unknown[] => {
  if (!Array.isArray(value)) throw new Error('店铺上下文响应缺少列表。')
  return value
}

const store = (value: unknown): WorkspaceStoreContext => {
  const item = record(value)
  return {
    storeId: integer(item.store_id), tenantId: text(item.tenant_id),
    platform: text(item.platform), storeCode: text(item.store_code),
    storeName: text(item.store_name), isDefault: boolean(item.is_default)
  }
}
const product = (value: unknown): ProductContextCandidate => {
  const item = record(value)
  return { productId: text(item.product_id), displayName: text(item.display_name) }
}
const sku = (value: unknown): SkuContextCandidate => {
  const item = record(value)
  return { skuId: text(item.sku_id), displayName: text(item.display_name) }
}

export function adaptWorkspaceContext(value: unknown): WorkspaceContext {
  const item = record(value)
  if (item.schema_version !== 'ai-cs.store-context.v1') throw new Error('店铺上下文版本不兼容。')
  const state = text(item.state)
  if (state !== 'READY' && state !== 'STORE_SELECTION_REQUIRED') throw new Error('店铺上下文状态无效。')
  const roles = array(item.roles).map((role) => text(role))
  if (!roles.length || roles.some((role) => !['ADMIN', 'OPERATOR', 'CUSTOMER_SERVICE'].includes(role))) {
    throw new Error('店铺上下文角色无效。')
  }
  return {
    userId: text(item.user_id), roles: roles as WorkspaceContext['roles'],
    allStoreAccess: boolean(item.all_store_access), state,
    stores: array(item.stores).map(store), effectiveStore: item.effective_store ? store(item.effective_store) : null
  }
}

export function adaptContextResolution(value: unknown): ContextResolution {
  const item = record(value)
  if (item.schema_version !== 'ai-cs.store-context.v1') throw new Error('商品上下文版本不兼容。')
  const status = text(item.status)
  if (![
    'RESOLVED', 'STORE_SELECTION_REQUIRED', 'PRODUCT_CONFIRMATION_REQUIRED',
    'SKU_CONFIRMATION_REQUIRED', 'UNKNOWN'
  ].includes(status)) throw new Error('商品上下文状态无效。')
  return {
    resolutionId: text(item.resolution_id), status: status as ContextResolution['status'],
    store: item.store ? store(item.store) : null,
    product: item.product ? product(item.product) : null,
    sku: item.sku ? sku(item.sku) : null,
    productCandidates: array(item.product_candidates).map(product),
    skuCandidates: array(item.sku_candidates).map(sku),
    reasonCode: text(item.reason_code), createdAt: text(item.created_at)
  }
}
