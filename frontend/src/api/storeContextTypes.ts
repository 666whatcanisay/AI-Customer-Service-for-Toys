import type { RoleName } from '@/auth/authSession'

export type ContextResolutionStatus =
  | 'RESOLVED'
  | 'STORE_SELECTION_REQUIRED'
  | 'PRODUCT_CONFIRMATION_REQUIRED'
  | 'SKU_CONFIRMATION_REQUIRED'
  | 'UNKNOWN'

export interface WorkspaceStoreContext {
  storeId: number
  tenantId: string
  platform: string
  storeCode: string
  storeName: string
  isDefault: boolean
}

export interface WorkspaceContext {
  userId: string
  roles: RoleName[]
  allStoreAccess: boolean
  state: 'READY' | 'STORE_SELECTION_REQUIRED'
  stores: WorkspaceStoreContext[]
  effectiveStore: WorkspaceStoreContext | null
}

export interface ProductContextCandidate { productId: string; displayName: string }
export interface SkuContextCandidate { skuId: string; displayName: string }

export interface ContextResolutionRequest {
  conversation: Array<{ role: 'CUSTOMER' | 'AGENT'; content: string }>
  storeId?: number | null
  confirmedProductId?: string | null
  confirmedSkuId?: string | null
}

export interface ContextResolution {
  resolutionId: string
  status: ContextResolutionStatus
  store: WorkspaceStoreContext | null
  product: ProductContextCandidate | null
  sku: SkuContextCandidate | null
  productCandidates: ProductContextCandidate[]
  skuCandidates: SkuContextCandidate[]
  reasonCode: string
  createdAt: string
}
