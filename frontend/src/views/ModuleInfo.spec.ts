import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it } from 'vitest'
import ModuleInfo from './ModuleInfo.vue'

const mountAt = async (moduleKey: string) => {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/modules/:moduleKey', component: ModuleInfo }]
  })
  await router.push(`/modules/${moduleKey}`)
  await router.isReady()
  return mount(ModuleInfo, { global: { plugins: [router, ElementPlus] } })
}

describe('ModuleInfo', () => {
  it('explains an unavailable module without presenting fake operations', async () => {
    const wrapper = await mountAt('product-query')
    expect(wrapper.text()).toContain('该模块当前尚不可用')
    expect(wrapper.text()).toContain('规划中')
    expect(wrapper.text()).not.toContain('立即执行')
  })

  it('shows the hard execution boundary for refund-like modules', async () => {
    const wrapper = await mountAt('refund-interception')
    expect(wrapper.get('[data-testid="execution-boundary"]').text()).toContain('不会自动退款')
    expect(wrapper.text()).toContain('不会自动发送消息')
  })
})
