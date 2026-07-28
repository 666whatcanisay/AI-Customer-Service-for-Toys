import { flushPromises, mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { CustomerIdentityKey } from '@/workspace/customerIdentity'
import SuggestionForm from './SuggestionForm.vue'

const apiMocks = vi.hoisted(() => ({ submit: vi.fn() }))
vi.mock('@/api/suggestionClient', () => ({ suggestionClient: { submit: apiMocks.submit } }))
vi.mock('vue-router', async () => {
  const actual = await vi.importActual<typeof import('vue-router')>('vue-router')
  return { ...actual, useRoute: () => ({ query: {} }) }
})

const mountPage = async () => {
  return mount(SuggestionForm, {
    global: {
      plugins: [ElementPlus],
      stubs: { RouterLink: { template: '<a><slot /></a>' } },
      provide: {
        [CustomerIdentityKey as symbol]: {
          identity: ref({ userId: 'CSU-ONE', displayName: '小木', role: 'CUSTOMER_SERVICE', status: 'ACTIVE', defaultStoreCode: 'PDD-SM', storeBindings: [{ storeCode: 'PDD-SM', isDefault: true }] })
        }
      }
    }
  })
}

describe('SuggestionForm', () => {
  beforeEach(() => apiMocks.submit.mockReset())

  it('validates required content before calling C', async () => {
    const wrapper = await mountPage()
    await wrapper.get('[data-testid="suggestion-submit"]').trigger('click')
    expect(wrapper.get('[data-testid="suggestion-validation"]').text()).toContain('标题')
    expect(apiMocks.submit).not.toHaveBeenCalled()
  })

  it('submits once while loading and shows the real receipt number', async () => {
    let resolveRequest!: (value: { suggestionId: string; status: string }) => void
    apiMocks.submit.mockReturnValue(new Promise((resolve) => { resolveRequest = resolve }))
    const wrapper = await mountPage()
    await wrapper.get('input[data-testid="suggestion-title"]').setValue('改进建议标题')
    await wrapper.get('textarea[data-testid="suggestion-description"]').setValue('这是一个只包含测试现象和期望结果的详细说明。')
    const button = wrapper.get('[data-testid="suggestion-submit"]')
    await button.trigger('click')
    await button.trigger('click')
    expect(apiMocks.submit).toHaveBeenCalledTimes(1)
    expect(apiMocks.submit.mock.calls[0][0]).toMatchObject({ reporterId: 'CSU-ONE', storeCode: 'PDD-SM' })
    resolveRequest({ suggestionId: 'SUG-001', status: 'SUBMITTED' })
    await flushPromises()
    expect(wrapper.get('[data-testid="suggestion-success"]').text()).toContain('SUG-001')
    expect(wrapper.text()).toContain('已提交')
  })

})
