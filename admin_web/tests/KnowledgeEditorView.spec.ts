import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import KnowledgeEditorView from '../src/views/KnowledgeEditorView.vue'
import { getProductKnowledgeOverview, getProductKnowledgeProduct, listProductKnowledgeProducts, uploadKnowledgeMaterial } from '../src/api/client'

vi.mock('vue-router', () => ({ useRoute: () => ({ query: { store: 'STORE-ONE', product: 'PRODUCT-ONE' } }) }))
vi.mock('../src/api/client', () => ({
  apiErrorMessage: vi.fn(() => '暂时不可用'),
  getProductKnowledgeOverview: vi.fn(),
  getProductKnowledgeProduct: vi.fn(),
  listProductKnowledgeProducts: vi.fn(),
  uploadKnowledgeMaterial: vi.fn(),
}))

const tech = { store_code: 'STORE-ONE', platform: 'pinduoduo', product_id: 'PRODUCT-ONE', product_code: null, sku_id: null, sku_code: null, source_id: null, material_id: null, revision: null, content_hash: null }

describe('KnowledgeEditorView', () => {
  it('submits Chinese product knowledge without asking the operator for technical fields', async () => {
    vi.mocked(getProductKnowledgeOverview).mockResolvedValue({ generated_at: '2026-07-29T00:00:00Z', has_data: true, stats: { store_count: 1, product_count: 1, ai_usable_product_count: 1, gap_count: 1, pending_review_count: 0 }, stores: [{ store_name: '木木小栈拼多多旗舰店', platform_name: '拼多多', product_count: 1, ai_usable_product_count: 1, gap_count: 1, pending_review_count: 0, technical_details: tech }], boundary_note: '不代表知识已发布到RAG。' })
    vi.mocked(listProductKnowledgeProducts).mockResolvedValue({ items: [{ store_name: '木木小栈拼多多旗舰店', product_name: 'Q66消防局积木', product_summary: '消防主题积木', core_selling_points: [], applicable_age: null, material_safety: null, package_contents: null, faq_count: 0, sku_names: ['豪华版'], coverage_percent: 40, ai_usable: true, knowledge_state: 'BASIC_AVAILABLE', data_status: 'DRAFT', ai_status: 'UNCONFIRMED', answerable_topics: ['商品名称'], missing_topics: ['适用年龄'], gap_count: 1, technical_details: tech }], total: 1 })
    vi.mocked(getProductKnowledgeProduct).mockResolvedValue({ store: { store_name: '木木小栈拼多多旗舰店', platform_name: '拼多多', product_count: 1, ai_usable_product_count: 1, gap_count: 1, pending_review_count: 0, technical_details: tech }, product: { product_name: 'Q66消防局积木', product_summary: null, core_selling_points: [], applicable_age: null, material: null, package_contents: null, usage_instructions: null, technical_details: tech }, skus: [{ sku_name: '豪华版', color_style: '红色', specification_difference: '含灯光组件', package_difference: null, faq_count: 0, difference_confirmed: true, attributes: [], technical_details: { ...tech, product_id: null, sku_id: 'SKU-ONE' } }], faqs: [], safety_information: [], sources: [], coverage_percent: 40, ai_usable: true, knowledge_state: 'BASIC_AVAILABLE', data_status: 'DRAFT', ai_status: 'UNCONFIRMED', topic_coverage: [], answerable_topics: [], missing_topics: [], gaps: [], next_actions: [], boundary_note: '不代表知识已发布到RAG。' })
    vi.mocked(uploadKnowledgeMaterial).mockResolvedValue({ material_id: 'KMT-1', revision: 1, content_hash: 'sha256:test', material_status: 'RECOGNIZED', recognition_summary: { readable: true, file_extension: '.json', detected_fields: ['商品简介', '资料来源'], missing_expected_fields: ['适用年龄'], privacy_reminder: '请去标识化', template_type: 'PRODUCT_KNOWLEDGE', template_name: '商品知识采集模板', record_count: 1, warnings: [], high_risk_source_confirmed: null } })

    const wrapper = mount(KnowledgeEditorView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()
    const text = wrapper.text()
    expect(text).toContain('中文知识维护')
    expect(text).toContain('SKU差异知识')
    expect(text).not.toContain('product_id')
    expect(text).not.toContain('tenant_id')

    await wrapper.get('textarea').setValue('消防主题机械积木。')
    const inputs = wrapper.findAll('input')
    await inputs.find((item) => item.attributes('type') === 'date')!.setValue('2026-07-20')
    const textInputs = inputs.filter((item) => !item.attributes('type') || item.attributes('type') === 'text')
    await textInputs[textInputs.length - 2].setValue('商品说明书第2页')
    await textInputs[textInputs.length - 1].setValue('运营测试')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(uploadKnowledgeMaterial).toHaveBeenCalledWith(expect.any(File), expect.objectContaining({ template_type: 'PRODUCT_KNOWLEDGE', material_type: 'PRODUCT_SPEC' }))
    expect(wrapper.text()).toContain('已保存为待审核资料')
  })
})
