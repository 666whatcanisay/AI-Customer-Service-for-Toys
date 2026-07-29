import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import KnowledgeMaterialsView from '../src/views/KnowledgeMaterialsView.vue'
import {
  getKnowledgeMaterial,
  getProductKnowledgeOverview,
  listKnowledgeMaterials,
  listProductKnowledgeProducts,
} from '../src/api/client'

vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }) }))

vi.mock('../src/api/client', () => ({
  apiErrorMessage: vi.fn(() => '资料服务暂时不可用'),
  getKnowledgeMaterial: vi.fn(),
  getProductKnowledgeOverview: vi.fn(),
  getProductKnowledgeProduct: vi.fn(),
  listKnowledgeMaterials: vi.fn(),
  listProductKnowledgeProducts: vi.fn(),
  reviewKnowledgeMaterial: vi.fn(),
  uploadKnowledgeMaterial: vi.fn(),
}))

const mockedList = vi.mocked(listKnowledgeMaterials)
const mockedDetail = vi.mocked(getKnowledgeMaterial)
const mockedOverview = vi.mocked(getProductKnowledgeOverview)
const mockedProducts = vi.mocked(listProductKnowledgeProducts)

const material = {
  material_id: 'KMT-TEST-1', revision: 1, store_code: 'STORE-ONE', product_id: 'PRODUCT-ONE', sku_id: null,
  material_type: 'PRODUCT_SPEC' as const, display_name: '积木规格说明', original_filename: 'spec.txt',
  content_hash: 'sha256:test', redaction_version: 'v1-reminder-only', material_status: 'RECOGNIZED' as const,
  recognition_summary: { readable: true, file_extension: '.xlsx', detected_fields: ['适用年龄'], missing_expected_fields: ['包装内容'], privacy_reminder: '请确认不包含客户隐私。', template_type: 'PRODUCT_KNOWLEDGE' as const, template_name: '商品知识采集模板', record_count: 1, warnings: [], high_risk_source_confirmed: null },
  submitted_by: '运营测试', reviewed_by: null, reviewed_at: null, review_note: null,
  created_at: '2026-07-28T00:00:00Z', updated_at: '2026-07-28T00:00:00Z',
}

describe('KnowledgeMaterialsView', () => {
  beforeEach(() => {
    mockedList.mockReset()
    mockedDetail.mockReset()
    mockedOverview.mockReset()
    mockedProducts.mockReset()
    mockedOverview.mockResolvedValue({
      generated_at: '2026-07-28T00:00:00Z', has_data: true,
      stats: { store_count: 1, product_count: 1, ai_usable_product_count: 1, gap_count: 2, pending_review_count: 1 },
      stores: [{
        store_name: '木木小栈拼多多旗舰店', platform_name: '拼多多', product_count: 1,
        ai_usable_product_count: 1, gap_count: 2, pending_review_count: 1,
        technical_details: { store_code: 'STORE-ONE', platform: 'pinduoduo', product_id: null, product_code: null, sku_id: null, sku_code: null, source_id: null, material_id: null, revision: null, content_hash: null },
      }], boundary_note: '不代表知识已发布到 RAG。',
    })
    mockedProducts.mockResolvedValue({
      items: [{
        store_name: '木木小栈拼多多旗舰店', product_name: 'Q66城市消防局机械积木玩具套装',
        product_summary: '消防主题机械积木。', core_selling_points: ['机械联动'], sku_names: ['豪华版'],
        applicable_age: '8—14 岁', material_safety: 'ABS', package_contents: '积木、说明书', faq_count: 1,
        coverage_percent: 80, ai_usable: true, knowledge_state: 'BASIC_AVAILABLE', answerable_topics: ['商品介绍'],
        data_status: 'APPROVED', ai_status: 'PARTIALLY_AVAILABLE',
        missing_topics: ['适用年龄'], gap_count: 1,
        technical_details: { store_code: 'STORE-ONE', platform: 'pinduoduo', product_id: 'PRODUCT-ONE', product_code: null, sku_id: null, sku_code: null, source_id: null, material_id: null, revision: null, content_hash: null },
      }], total: 1,
    })
    mockedList.mockResolvedValue({ items: [material], total: 1, page: 1, size: 20 })
    mockedDetail.mockResolvedValue({ ...material, analysis_text_preview: '适用年龄：6-12岁。' })
  })

  it('shows the Chinese controlled upload workflow and never advertises automatic publication', async () => {
    const wrapper = mount(KnowledgeMaterialsView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    expect(wrapper.text()).toContain('资料上传与审核')
    expect(wrapper.text()).toContain('下载中文资料模板')
    expect(wrapper.text()).toContain('不会自动发布')
    expect(wrapper.text()).toContain('木木小栈拼多多旗舰店')
    expect(wrapper.text()).toContain('Q66城市消防局机械积木玩具套装')
    expect(wrapper.text()).toContain('积木规格说明')
    expect(wrapper.text()).toContain('已识别，待审核')
    expect(wrapper.text()).not.toContain('RECOGNIZED')
    expect(wrapper.text()).not.toContain('自动训练')

    await wrapper.get('.link-button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('人工核对')
    expect(wrapper.text()).toContain('适用年龄：6-12岁。')
    expect(wrapper.text()).not.toContain('raw_storage_path')
  })
})
