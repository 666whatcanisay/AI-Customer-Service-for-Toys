import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import ProductDetailView from '../src/views/ProductDetailView.vue'
import { getProductKnowledgeProduct, updateProductBasicInfo, type ProductKnowledgeDetail } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  apiErrorMessage: vi.fn(() => '暂时不可用'),
  checkProductAiKnowledge: vi.fn(),
  getProductKnowledgeProduct: vi.fn(),
  listCatalogActivationReceipts: vi.fn(),
  listProductAiKnowledgeReceipts: vi.fn(),
  publishProductAiKnowledge: vi.fn(),
  setProductCustomerServiceStatus: vi.fn(),
  updateProductBasicInfo: vi.fn(),
}))

vi.mock('../src/presentation', () => ({ displayStatus: (value: string) => value }))

const tech = { store_code: 'mumu-pdd', platform: 'pinduoduo', product_id: 'PRODUCT-Q66', product_code: null, sku_id: null, sku_code: null, source_id: null, material_id: null, revision: null, content_hash: null }

describe('ProductDetailView', () => {
  it('answers the three operator questions and preserves the missing-age fallback', async () => {
    const productDetail = {
      store: { store_name: '木木小栈拼多多旗舰店', platform_name: '拼多多', product_count: 1, ai_usable_product_count: 1, gap_count: 1, pending_review_count: 0, technical_details: tech },
      product: { product_name: 'Q66城市消防局机械积木玩具套装', product_summary: '消防主题机械积木。', core_selling_points: ['机械联动'], applicable_age: null, material: 'ABS', package_contents: '积木、说明书', usage_instructions: '按步骤拼装', data_source: 'PILOT', customer_service_status: 'DISABLED', customer_service_status_updated_at: null, customer_service_status_updated_by: null, technical_details: tech },
      skus: [{ sku_name: '豪华版', color_style: '红色', specification_difference: '含灯光组件', package_difference: '独立彩盒', faq_count: 1, difference_confirmed: true, attributes: ['颜色：红色'], technical_details: { ...tech, product_id: null, sku_id: 'SKU-L', sku_code: 'Q66-L' } }],
      faqs: [{ question: '有什么特点？', recommended_reply: '消防主题，支持机械联动。', answer_strategy: 'DIRECT_ANSWER', risk_level: 'LOW', sku_name: null }],
      safety_information: [{ title: '安全说明', content: '含小零件，需成人陪同。', risk_level: 'MEDIUM', forbidden_claim: '不得承诺绝对安全', handoff_condition: '发生误食时转人工' }],
      sources: [{ source_name: '商品说明书', source_type: 'PRODUCT_MANUAL', review_status: 'APPROVED', technical_details: { ...tech, product_id: null, source_id: 'SRC-1', content_hash: 'hash' } }],
      coverage_percent: 78, ai_usable: true, knowledge_state: 'BASIC_AVAILABLE',
      data_status: 'APPROVED', ai_status: 'PARTIALLY_AVAILABLE',
      ai_knowledge: { status: 'NOT_GENERATED', embedding_status: 'NOT_GENERATED', current_fingerprint: 'current', indexed_fingerprint: null, active_collection: null, chunk_count: 0, embedding_count: 0, updated_at: null, published_at: null, last_error_code: null },
      topic_coverage: [
        { key: 'product_summary', name: '商品介绍', level: 'A', status: 'SUPPORTED', evidence_summary: '结构化资料' },
        { key: 'age', name: '适用年龄', level: 'A', status: 'MISSING', evidence_summary: null },
        { key: 'sku_difference', name: 'SKU区别', level: 'B', status: 'SUPPORTED', evidence_summary: null },
      ],
      answerable_topics: ['商品介绍', 'SKU区别'], missing_topics: ['适用年龄'],
      gaps: [{ key: 'MISSING_AGE', title: '缺少适用年龄', severity: 'HIGH', description: '不能稳妥回答年龄问题。', recommended_action: '补充并审核适用年龄资料。', safe_fallback: '当前资料未提供年龄信息，建议人工确认。', source: 'C_COVERAGE_RULE' }],
      next_actions: ['补充并审核适用年龄资料。'], boundary_note: '此处展示资料可回答能力，不代表知识已发布到 RAG。',
    } satisfies ProductKnowledgeDetail
    vi.mocked(getProductKnowledgeProduct).mockResolvedValue(productDetail)

    const wrapper = mount(ProductDetailView, { props: { productId: 'PRODUCT-Q66' }, global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    expect(wrapper.text()).toContain('1. AI 现在能回答什么？')
    expect(wrapper.text()).toContain('2. AI 不能回答什么？')
    expect(wrapper.text()).toContain('3. 运营下一步补什么？')
    expect(wrapper.text()).toContain('豪华版')
    expect(wrapper.text()).toContain('含灯光组件')
    expect(wrapper.text()).toContain('当前资料未提供年龄信息，建议人工确认。')
    expect(wrapper.text()).toContain('不代表知识已发布到 RAG')
    expect(wrapper.text()).toContain('客服：已禁用')
    expect(wrapper.text()).toContain('AI知识：未生成')
    expect(wrapper.text()).toContain('AI 知识发布')

    const editButton = wrapper.findAll('button').find((item) => item.text() === '编辑基础信息')
    await editButton!.trigger('click')
    expect(wrapper.text()).toContain('商品展示名称')
    expect(wrapper.text()).toContain('店铺展示名称')
    expect(wrapper.text()).toContain('商品和 SKU 的内部身份不会改变')

    const updatedDetail: ProductKnowledgeDetail = {
      ...productDetail,
      store: { ...productDetail.store, store_name: '木木小栈玩具旗舰店', remarks: '展示备注' },
      product: { ...productDetail.product, product_name: 'Q66消防局机械积木', product_summary: '更新后的商品简介。' },
      data_status: 'PENDING_REVIEW',
    }
    vi.mocked(updateProductBasicInfo).mockResolvedValue(updatedDetail)
    const inputs = wrapper.findAll('.basic-info-form input')
    const textareas = wrapper.findAll('.basic-info-form textarea')
    await inputs[0].setValue('Q66消防局机械积木')
    await inputs[1].setValue('木木小栈玩具旗舰店')
    await textareas[0].setValue('更新后的商品简介。')
    await textareas[1].setValue('展示备注')
    await wrapper.get('.basic-info-form').trigger('submit')
    await flushPromises()

    expect(updateProductBasicInfo).toHaveBeenCalledWith('PRODUCT-Q66', {
      product_display_name: 'Q66消防局机械积木',
      product_summary: '更新后的商品简介。',
      store_display_name: '木木小栈玩具旗舰店',
      store_remarks: '展示备注',
    })
    expect(wrapper.text()).toContain('基础信息已保存并同步显示')
    expect(wrapper.text()).toContain('Q66消防局机械积木')
  })
})
