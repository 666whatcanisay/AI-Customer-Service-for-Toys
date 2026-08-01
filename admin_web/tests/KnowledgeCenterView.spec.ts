import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import KnowledgeCenterView from '../src/views/KnowledgeCenterView.vue'
import { enableProductsForCustomerService, getProductKnowledgeOverview, listProductKnowledgeProducts, publishProductAiKnowledge } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  apiErrorMessage: vi.fn(() => '暂时不可用'),
  getProductKnowledgeOverview: vi.fn(),
  listProductKnowledgeProducts: vi.fn(),
  enableProductsForCustomerService: vi.fn(),
  publishProductAiKnowledge: vi.fn(),
}))

const technicalDetails = {
  store_code: 'mumu-pdd', platform: 'pinduoduo', product_id: 'PRODUCT-Q66', product_code: 'Q66',
  sku_id: null, sku_code: null, source_id: null, material_id: null, revision: null, content_hash: null,
}

describe('KnowledgeCenterView', () => {
  beforeEach(() => {
    vi.mocked(getProductKnowledgeOverview).mockResolvedValue({
      generated_at: '2026-07-28T00:00:00Z', has_data: true,
      stats: { store_count: 1, product_count: 1, ai_usable_product_count: 1, gap_count: 2, pending_review_count: 1 },
      stores: [{ store_name: '木木小栈拼多多旗舰店', platform_name: '拼多多', product_count: 1, ai_usable_product_count: 1, gap_count: 2, pending_review_count: 1, technical_details: { ...technicalDetails, product_id: null, product_code: null } }],
      boundary_note: '此处展示资料可回答能力，不代表知识已发布到 RAG。',
    })
    vi.mocked(listProductKnowledgeProducts).mockResolvedValue({
      items: [{
        store_name: '木木小栈拼多多旗舰店', product_name: 'Q66城市消防局机械积木玩具套装',
        product_summary: '城市消防主题机械积木套装。', core_selling_points: ['机械联动', '消防玩法'], sku_names: ['豪华版', '标准版'],
        applicable_age: '8—14 岁', material_safety: 'ABS，含小零件', package_contents: '积木、说明书', faq_count: 2,
        coverage_percent: 80, ai_usable: true, knowledge_state: 'BASIC_AVAILABLE',
        data_status: 'APPROVED', ai_status: 'PARTIALLY_AVAILABLE',
        ai_knowledge: { status: 'NOT_GENERATED', embedding_status: 'NOT_GENERATED', current_fingerprint: 'current', indexed_fingerprint: null, active_collection: null, chunk_count: 0, embedding_count: 0, updated_at: null, published_at: null, last_error_code: null },
        data_source: 'TEST', customer_service_status: 'ENABLED', customer_service_status_updated_at: null, customer_service_status_updated_by: null,
        answerable_topics: ['商品介绍', '年龄咨询', '材质说明'], missing_topics: ['安装说明', '常见问题'], gap_count: 2,
        technical_details: technicalDetails,
      }], total: 1,
    })
  })

  it('shows source-backed statistics and the store-product-sku business hierarchy', async () => {
    const wrapper = mount(KnowledgeCenterView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    expect(wrapper.text()).toContain('商品知识中心')
    expect(wrapper.text()).toContain('AI 可用商品1')
    expect(wrapper.text()).toContain('木木小栈拼多多旗舰店')
    expect(wrapper.text()).toContain('Q66城市消防局机械积木玩具套装')
    expect(wrapper.text()).toContain('Q66城市消防局机械积木玩具套装 → 豪华版')
    expect(wrapper.text()).toContain('80%AI 核心知识覆盖度')
    expect(wrapper.text()).toContain('资料：已审核')
    expect(wrapper.text()).toContain('客服：可用')
    expect(wrapper.text()).toContain('AI知识：未发布')
    expect(wrapper.text()).toContain('下一步发布 AI 知识')
    expect(wrapper.find('.product-business-details').attributes('open')).toBeUndefined()
    expect(wrapper.find('.product-technical-details').attributes('open')).toBeUndefined()
    expect(wrapper.find('.product-technical-details').text()).toContain('知识片段0')
    expect(wrapper.text()).not.toContain('tenant_id')
  })

  it('explains loading and full-page failure states with a next action', async () => {
    vi.mocked(getProductKnowledgeOverview).mockReturnValueOnce(new Promise(() => {}))
    const loadingWrapper = mount(KnowledgeCenterView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    expect(loadingWrapper.get('[data-testid="knowledge-loading-state"]').text()).toContain('正在汇总商品知识')
    expect(loadingWrapper.get('[data-testid="knowledge-loading-state"]').text()).toContain('下一步：')

    vi.mocked(getProductKnowledgeOverview).mockRejectedValueOnce(new Error('知识接口连接失败'))
    const errorWrapper = mount(KnowledgeCenterView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()
    expect(errorWrapper.get('[data-testid="knowledge-error-state"]').text()).toContain('商品知识暂时无法读取')
    expect(errorWrapper.get('[data-testid="knowledge-error-state"]').text()).toContain('原因：暂时不可用')
    expect(errorWrapper.get('[data-testid="knowledge-error-state"]').text()).toContain('重新读取')
  })

  it('batch enables approved products and exposes explicit AI publish action', async () => {
    const disabled = await listProductKnowledgeProducts()
    disabled.items[0].customer_service_status = 'DISABLED'
    const enabled = {
      ...disabled,
      items: [{ ...disabled.items[0], customer_service_status: 'ENABLED' as const }],
    }
    vi.mocked(listProductKnowledgeProducts).mockResolvedValueOnce(disabled).mockResolvedValue(enabled)
    vi.mocked(enableProductsForCustomerService).mockResolvedValue({
      schema_version: 'pilot-business-catalog-batch-activation.v1', result_status: 'COMPLETE', target_status: 'ENABLED',
      items: [], changed_count: 1, unchanged_count: 0, failed_count: 0, server_time: '2026-07-31T00:00:00Z',
    })
    vi.mocked(publishProductAiKnowledge).mockResolvedValue({
      schema_version: 'product-knowledge-publication.v1', changed: true, product_id: 'PRODUCT-Q66',
      ai_knowledge: { ...disabled.items[0].ai_knowledge, status: 'PUBLISHED', embedding_status: 'COMPLETE', chunk_count: 2, embedding_count: 2 },
      publication_receipt: { publication_receipt_id: 'RAG-1', product_id: 'PRODUCT-Q66', knowledge_fingerprint: 'current', active_collection: 'test', chunk_count: 2, embedding_count: 2, status: 'PUBLISHED', operator: '运营A', created_at: '2026-07-31T00:00:00Z' },
    })

    const confirm = vi.spyOn(window, 'confirm').mockReturnValue(true)
    const wrapper = mount(KnowledgeCenterView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()
    expect(wrapper.get('[data-testid="pending-enable-count"]').text()).toContain('当前待启用：1 个')
    expect(wrapper.text()).toContain('下一步启用客服使用')
    await wrapper.get('[data-testid="knowledge-activation-operator"]').setValue('运营A')
    await wrapper.get('[data-testid="select-all-filtered-products"]').setValue(true)
    expect(wrapper.get('[data-testid="batch-enable-products"]').text()).toContain('批量启用客服（1）')
    await wrapper.get('[data-testid="batch-enable-products"]').trigger('click')
    await flushPromises()
    expect(confirm).toHaveBeenCalledWith('确认启用当前选择的 1 个商品供客服使用？')
    expect(enableProductsForCustomerService).toHaveBeenCalledWith(['PRODUCT-Q66'], '运营A', expect.stringContaining('batch-enable-'))
    expect(wrapper.text()).toContain('客服工作台刷新目录后即可使用')
    expect(wrapper.text()).toContain('下一步发布 AI 知识')

    await wrapper.get('[data-testid="publish-product-PRODUCT-Q66"]').trigger('click')
    await flushPromises()
    expect(publishProductAiKnowledge).toHaveBeenCalledWith('PRODUCT-Q66', '运营A', expect.stringContaining('publish-PRODUCT-Q66-'))
    confirm.mockRestore()
  })

  it('uses 暂无统计 instead of inventing metrics when there is no data', async () => {
    vi.mocked(getProductKnowledgeOverview).mockResolvedValueOnce({
      generated_at: '2026-07-28T00:00:00Z', has_data: false,
      stats: { store_count: null, product_count: null, ai_usable_product_count: null, gap_count: null, pending_review_count: null },
      stores: [], boundary_note: '不代表知识已发布到 RAG。',
    })
    const wrapper = mount(KnowledgeCenterView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    expect(wrapper.text().match(/暂无统计/g)).toHaveLength(5)
    expect(wrapper.text()).toContain('页面不会生成示例统计或虚构商品')
    expect(wrapper.get('[data-testid="knowledge-empty-state"]').text()).toContain('下一步：')
  })
})
