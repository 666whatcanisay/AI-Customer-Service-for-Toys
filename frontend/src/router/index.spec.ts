import { createMemoryHistory } from 'vue-router'
import { describe, expect, it } from 'vitest'
import { createCustomerRouter } from './index'
import { authSessionTestControl } from '@/auth/authSession'

describe('customer workbench router', () => {
  it('registers the frozen workbench routes', () => {
    const paths = createCustomerRouter(createMemoryHistory(), false).getRoutes().map((route) => route.path)

    expect(paths).toEqual(expect.arrayContaining([
      '/', '/login', '/forbidden', '/change-password', '/store-selection', '/workspace', '/ai-chat', '/suggestions', '/suggestions/mine', '/experience-cases', '/feedback', '/modules/:moduleKey'
    ]))
  })

  it('keeps old entry links compatible without aliasing the home route', async () => {
    const router = createCustomerRouter(createMemoryHistory(), false)
    await router.push('/chat')
    await router.isReady()
    expect(router.currentRoute.value.path).toBe('/ai-chat')
  })

  it('keeps the feedback guidance route available without changing the AI chat workflow', async () => {
    const router = createCustomerRouter(createMemoryHistory(), false)
    await router.push('/feedback')
    await router.isReady()

    expect(router.currentRoute.value.name).toBe('FeedbackGuide')
  })

  it('requires a real session and server permission for workspace routes', async () => {
    authSessionTestControl.reset()
    const anonymousRouter = createCustomerRouter(createMemoryHistory())
    await anonymousRouter.push('/workspace')
    await anonymousRouter.isReady()
    expect(anonymousRouter.currentRoute.value.path).toBe('/login')

    authSessionTestControl.setUser({
      id: '22222222-2222-4222-8222-222222222222', username: 'operator.one',
      display_name: '运营一号', status: 'ACTIVE', roles: ['OPERATOR'],
      permissions: ['product.manage'], stores: [],
      must_change_password: false, all_store_access: true,
      created_at: '2026-08-06T00:00:00Z', updated_at: '2026-08-06T00:00:00Z'
    })
    const operatorRouter = createCustomerRouter(createMemoryHistory())
    await operatorRouter.push('/workspace')
    await operatorRouter.isReady()
    expect(operatorRouter.currentRoute.value.path).toBe('/forbidden')

    authSessionTestControl.setUser({
      id: '33333333-3333-4333-8333-333333333333', username: 'support.one',
      display_name: '客服一号', status: 'ACTIVE', roles: ['CUSTOMER_SERVICE'],
      permissions: ['workspace.access'], stores: [],
      must_change_password: false, all_store_access: false,
      created_at: '2026-08-06T00:00:00Z', updated_at: '2026-08-06T00:00:00Z'
    })
    const supportRouter = createCustomerRouter(createMemoryHistory())
    await supportRouter.push('/workspace')
    await supportRouter.isReady()
    expect(supportRouter.currentRoute.value.path).toBe('/store-selection')

    authSessionTestControl.setUser({
      id: '33333333-3333-4333-8333-333333333333', username: 'support.one',
      display_name: '客服一号', status: 'ACTIVE', roles: ['CUSTOMER_SERVICE'],
      permissions: ['workspace.access'],
      stores: [{ id: 1, store_id: 1, store_code: 'STORE-1', store_name: '一店', platform: 'pdd', is_default: true }],
      must_change_password: false, all_store_access: false,
      created_at: '2026-08-06T00:00:00Z', updated_at: '2026-08-06T00:00:00Z'
    })
    const boundSupportRouter = createCustomerRouter(createMemoryHistory())
    await boundSupportRouter.push('/workspace')
    await boundSupportRouter.isReady()
    expect(boundSupportRouter.currentRoute.value.path).toBe('/workspace')
    authSessionTestControl.reset()
  })

  it('forces password replacement before every business route', async () => {
    authSessionTestControl.setUser({
      id: '44444444-4444-4444-8444-444444444444', username: 'Wa', display_name: '客服主管',
      status: 'ACTIVE', roles: ['CUSTOMER_SERVICE'], permissions: ['workspace.access'], stores: [],
      must_change_password: true, all_store_access: false,
      created_at: '2026-08-06T00:00:00Z', updated_at: '2026-08-06T00:00:00Z'
    })
    const router = createCustomerRouter(createMemoryHistory())
    await router.push('/workspace'); await router.isReady()
    expect(router.currentRoute.value.path).toBe('/change-password')
    authSessionTestControl.reset()
  })
})
