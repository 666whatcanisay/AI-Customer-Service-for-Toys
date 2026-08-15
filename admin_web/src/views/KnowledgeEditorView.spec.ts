import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  apiErrorMessage: vi.fn((reason: unknown) => String(reason)),
  getKnowledgeMaterialDiff: vi.fn(),
  getKnowledgeMaterialRevision: vi.fn(),
  getProductKnowledgeOverview: vi.fn(),
  getProductKnowledgeProduct: vi.fn(),
  getReplyReadinessQuestionSet: vi.fn(),
  listKnowledgeMaterialRevisions: vi.fn(),
  listProductKnowledgeProducts: vi.fn(),
  uploadKnowledgeMaterial: vi.fn(),
}))

vi.mock('../api/client', () => apiMocks)

import KnowledgeEditorView from './KnowledgeEditorView.vue'

async function mountView(path = '/knowledge-editor') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/knowledge-editor', component: KnowledgeEditorView },
      { path: '/knowledge-review', component: { template: '<div />' } },
      { path: '/reply-readiness', component: { template: '<div />' } },
    ],
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount({ template: '<RouterView />', components: { RouterView } }, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('KnowledgeEditorView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.getProductKnowledgeOverview.mockResolvedValue({
      stores: [{ store_name: '正式店铺', technical_details: { store_code: 'STORE' } }],
    })
    apiMocks.listProductKnowledgeProducts.mockResolvedValue({
      items: [{ product_name: '正式商品', data_source: 'INITIAL_IMPORT', technical_details: { store_code: 'STORE', product_id: 'PRODUCT' } }],
    })
  })

  it('loads the editor with the governed store catalog and four knowledge templates', async () => {
    const wrapper = await mountView()

    expect(wrapper.text()).toContain('知识编辑器')
    expect(wrapper.text()).toContain('正式店铺')
    expect(wrapper.findAll('[aria-label="知识模板类型"] input[type="radio"]')).toHaveLength(4)
    expect(wrapper.text()).toContain('商品知识')
    expect(wrapper.text()).toContain('SKU差异知识')
    expect(wrapper.text()).toContain('客服FAQ')
    expect(wrapper.text()).toContain('商品安全规则')
  })

  it('rejects synthetic fixture deep links that do not belong to the governed catalog', async () => {
    const wrapper = await mountView('/knowledge-editor?store=STORE-READINESS&product=PRODUCT-READINESS')

    expect(wrapper.text()).toContain('链接中的商品不属于当前店铺，请重新选择。')
    const store = wrapper.get('select')
    expect((store.element as HTMLSelectElement).value).toBe('')
  })
})
