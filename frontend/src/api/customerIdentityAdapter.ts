import {
  CUSTOMER_USER_ROLES,
  CUSTOMER_USER_STATUSES,
  type CustomerIdentity,
  type CustomerUserRole,
  type CustomerUserStatus,
} from './customerIdentityTypes'

type UnknownRecord = Record<string, unknown>

export class CustomerIdentityAdapterError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'CustomerIdentityAdapterError'
  }
}

const isRecord = (value: unknown): value is UnknownRecord =>
  typeof value === 'object' && value !== null && !Array.isArray(value)

const requiredText = (record: UnknownRecord, key: string, entity: string): string => {
  const value = record[key]
  if (typeof value !== 'string' || !value.trim()) {
    throw new CustomerIdentityAdapterError(`C ${entity}缺少有效字段 ${key}`)
  }
  return value.trim()
}

const enumValue = <T extends string>(
  record: UnknownRecord,
  key: string,
  accepted: readonly T[],
  entity: string,
): T => {
  const value = requiredText(record, key, entity)
  if (!accepted.includes(value as T)) {
    throw new CustomerIdentityAdapterError(`C ${entity}返回了不支持的 ${key}`)
  }
  return value as T
}

const adaptIdentity = (value: unknown): CustomerIdentity => {
  if (!isRecord(value)) throw new CustomerIdentityAdapterError('C 客服身份记录格式无效')
  const userId = requiredText(value, 'user_id', '客服身份')
  const defaultStoreCode = requiredText(value, 'default_store_code', '客服身份')
  const rawBindings = value.store_bindings
  if (!Array.isArray(rawBindings) || rawBindings.length === 0) {
    throw new CustomerIdentityAdapterError('C 客服身份必须返回至少一个已绑定店铺')
  }
  const storeBindings = rawBindings.map((binding) => {
    if (!isRecord(binding) || typeof binding.is_default !== 'boolean') {
      throw new CustomerIdentityAdapterError('C 客服身份返回了无效店铺绑定')
    }
    return { storeCode: requiredText(binding, 'store_code', '店铺绑定'), isDefault: binding.is_default }
  })
  if (!storeBindings.some((binding) => binding.storeCode === defaultStoreCode && binding.isDefault)) {
    throw new CustomerIdentityAdapterError('C 客服身份的默认店铺与店铺绑定不一致')
  }
  return {
    userId,
    displayName: requiredText(value, 'display_name', '客服身份'),
    role: enumValue(value, 'role', CUSTOMER_USER_ROLES, '客服身份') as CustomerUserRole,
    status: enumValue(value, 'status', CUSTOMER_USER_STATUSES, '客服身份') as CustomerUserStatus,
    defaultStoreCode,
    storeBindings,
  }
}

export const adaptCustomerIdentity = (payload: unknown): CustomerIdentity => adaptIdentity(payload)

export const adaptCustomerIdentityList = (payload: unknown): CustomerIdentity[] => {
  if (!isRecord(payload) || !Array.isArray(payload.items) || typeof payload.total !== 'number') {
    throw new CustomerIdentityAdapterError('C 客服身份接口必须返回 {items,total}')
  }
  const identities = payload.items.map(adaptIdentity)
  if (payload.total !== identities.length) {
    throw new CustomerIdentityAdapterError('C 客服身份列表总数与实际记录数不一致')
  }
  if (identities.some((identity) => identity.status !== 'ACTIVE')) {
    throw new CustomerIdentityAdapterError('客服身份选择接口不得返回已停用身份')
  }
  return identities
}
