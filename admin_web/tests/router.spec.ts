import { describe, expect, it } from 'vitest'

import { router } from '../src/router'


describe('internal production routes', () => {
  it('keeps every former navigation route and hides legacy test tools by default', () => {
    const paths = router.getRoutes().map((route) => route.path)

    expect(paths).toEqual(expect.arrayContaining([
      '/overview',
      '/ai-capabilities',
      '/store-management',
      '/knowledge-center',
      '/knowledge-editor',
      '/knowledge-review',
      '/knowledge-gaps',
      '/knowledge-materials',
      '/faqs',
      '/safety-rules',
      '/import-center',
      '/customer-operations',
      '/ai-issues',
      '/system-status',
      '/login',
      '/forbidden',
      '/change-password',
      '/user-management',
    ]))
    expect(paths).not.toContain('/imports')
    expect(paths).not.toContain('/imports/new')
    expect(paths).not.toContain('/imports/:batchId')
    expect(paths).not.toContain('/test-data-packages')
  })
})
