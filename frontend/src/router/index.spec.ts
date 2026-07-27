import { createMemoryHistory } from 'vue-router'
import { describe, expect, it } from 'vitest'
import { createCustomerRouter } from './index'

describe('customer workbench router', () => {
  it('registers the frozen workbench routes', () => {
    const paths = createCustomerRouter(createMemoryHistory()).getRoutes().map((route) => route.path)

    expect(paths).toEqual(expect.arrayContaining([
      '/', '/ai-chat', '/suggestions', '/suggestions/mine', '/experience-cases', '/feedback', '/modules/:moduleKey'
    ]))
  })

  it('keeps old entry links compatible without aliasing the home route', async () => {
    const router = createCustomerRouter(createMemoryHistory())
    await router.push('/chat')
    await router.isReady()
    expect(router.currentRoute.value.path).toBe('/ai-chat')
  })

  it('keeps the feedback guidance route available without changing the AI chat workflow', async () => {
    const router = createCustomerRouter(createMemoryHistory())
    await router.push('/feedback')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('FeedbackGuide')
  })
})
