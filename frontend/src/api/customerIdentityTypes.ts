export const CUSTOMER_USER_ROLES = ['CUSTOMER_SERVICE', 'OPERATIONS', 'ADMIN'] as const
export const CUSTOMER_USER_STATUSES = ['ACTIVE', 'DISABLED'] as const

export type CustomerUserRole = (typeof CUSTOMER_USER_ROLES)[number]
export type CustomerUserStatus = (typeof CUSTOMER_USER_STATUSES)[number]

export interface CustomerStoreBinding {
  storeCode: string
  isDefault: boolean
}

export interface CustomerIdentity {
  userId: string
  displayName: string
  role: CustomerUserRole
  status: CustomerUserStatus
  defaultStoreCode: string
  storeBindings: CustomerStoreBinding[]
}

export interface CustomerIdentityClient {
  list(signal?: AbortSignal): Promise<CustomerIdentity[]>
  get(userId: string, signal?: AbortSignal): Promise<CustomerIdentity>
}
