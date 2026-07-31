import { describe, expect, it } from 'vitest'

import { router } from '../src/router'


describe('internal production routes', () => {
  it('keeps operational routes and hides legacy test tools by default', () => {
    const paths = router.getRoutes().map((route) => route.path)

    expect(paths).toContain('/knowledge-materials')
    expect(paths).toContain('/import-center')
    expect(paths).not.toContain('/imports')
    expect(paths).not.toContain('/imports/new')
    expect(paths).not.toContain('/imports/:batchId')
    expect(paths).not.toContain('/test-data-packages')
  })
})
