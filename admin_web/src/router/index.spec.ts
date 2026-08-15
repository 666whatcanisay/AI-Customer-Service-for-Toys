import { describe, expect, it } from 'vitest'

import { router } from './index'

describe('knowledge governance route permissions', () => {
  it('requires knowledge.manage for the reply risk pool and knowledge editor', () => {
    expect(router.resolve('/reply-readiness').meta.requiredPermission).toBe('knowledge.manage')
    expect(router.resolve('/knowledge-editor').meta.requiredPermission).toBe('knowledge.manage')
  })
})
