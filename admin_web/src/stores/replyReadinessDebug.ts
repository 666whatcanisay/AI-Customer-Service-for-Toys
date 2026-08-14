import { reactive } from 'vue'

import type { ReplyReadinessPublishedDebugResult } from '../api/client'

export type ReplyReadinessWorkspaceTab = 'POOL' | 'DEBUG'

export interface ReplyReadinessDebugScope {
  store_code: string
  product_id: string
  sku_id: string
}

function emptyScope(): ReplyReadinessDebugScope {
  return { store_code: '', product_id: '', sku_id: '' }
}

export const replyReadinessDebugState = reactive({
  tab: 'POOL' as ReplyReadinessWorkspaceTab,
  scope: emptyScope(),
  customerMessage: '',
  latestMessage: '',
  previousResult: null as ReplyReadinessPublishedDebugResult | null,
  latestResult: null as ReplyReadinessPublishedDebugResult | null,
})

export function rememberReplyReadinessDebugScope(
  value: ReplyReadinessDebugScope,
): void {
  const changed = value.store_code !== replyReadinessDebugState.scope.store_code
    || value.product_id !== replyReadinessDebugState.scope.product_id
    || value.sku_id !== replyReadinessDebugState.scope.sku_id
  Object.assign(replyReadinessDebugState.scope, value)
  if (changed) {
    replyReadinessDebugState.previousResult = null
    replyReadinessDebugState.latestResult = null
    replyReadinessDebugState.latestMessage = ''
  }
}

export function resetReplyReadinessDebugState(): void {
  replyReadinessDebugState.tab = 'POOL'
  Object.assign(replyReadinessDebugState.scope, emptyScope())
  replyReadinessDebugState.customerMessage = ''
  replyReadinessDebugState.latestMessage = ''
  replyReadinessDebugState.previousResult = null
  replyReadinessDebugState.latestResult = null
}
