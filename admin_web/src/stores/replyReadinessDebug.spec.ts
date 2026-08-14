import { beforeEach, describe, expect, it } from 'vitest'

import { clearAdminSession } from '../auth/session'
import {
  replyReadinessDebugState,
  resetReplyReadinessDebugState,
} from './replyReadinessDebug'

describe('replyReadinessDebugState', () => {
  beforeEach(() => resetReplyReadinessDebugState())

  it('is cleared when the Admin session is cleared', () => {
    replyReadinessDebugState.tab = 'DEBUG'
    replyReadinessDebugState.scope.store_code = 'STORE-SYNTHETIC'
    replyReadinessDebugState.customerMessage = '你好'

    clearAdminSession()

    expect(replyReadinessDebugState.tab).toBe('POOL')
    expect(replyReadinessDebugState.scope.store_code).toBe('')
    expect(replyReadinessDebugState.customerMessage).toBe('')
    expect(replyReadinessDebugState.latestMessage).toBe('')
    expect(replyReadinessDebugState.latestResult).toBeNull()
  })
})
