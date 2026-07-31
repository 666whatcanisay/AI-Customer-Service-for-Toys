import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import KnowledgeReviewView from '../src/views/KnowledgeReviewView.vue'

const apiMocks = vi.hoisted(() => ({
  apiErrorMessage: vi.fn(() => '知识资料服务暂时不可用'),
  getKnowledgeMaterial: vi.fn(),
  listKnowledgeMaterials: vi.fn(),
  reviewKnowledgeMaterial: vi.fn(),
}))

vi.mock('vue-router', () => ({ useRoute: () => ({ query: { product: 'PRODUCT-ONE' } }) }))
vi.mock('../src/api/client', () => apiMocks)

const material = {
  material_id: 'KMT-ONE', revision: 1, store_code: 'STORE-ONE', product_id: 'PRODUCT-ONE', sku_id: null,
  material_type: 'PRODUCT_SPEC', display_name: '积木商品知识补充', original_filename: '补充.json',
  content_hash: 'sha256:test', redaction_version: 'none',
  recognition_summary: {
    readable: true, file_extension: '.json', detected_fields: ['商品简介'], missing_expected_fields: [],
    privacy_reminder: '不得包含客户隐私', template_type: 'PRODUCT_KNOWLEDGE', template_name: '商品知识',
    record_count: 1, warnings: [], high_risk_source_confirmed: true,
  },
  material_status: 'RECOGNIZED', submitted_by: '运营', reviewed_by: null, reviewed_at: null,
  review_note: null, created_at: '2026-07-31T00:00:00Z', updated_at: '2026-07-31T00:00:00Z',
}

describe('KnowledgeReviewView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.listKnowledgeMaterials.mockResolvedValue({ items: [material], total: 1, page: 1, size: 100 })
    apiMocks.getKnowledgeMaterial.mockResolvedValue({ ...material, analysis_text_preview: '{"商品简介":"机关山洞场景积木"}' })
    apiMocks.reviewKnowledgeMaterial.mockResolvedValue({ ...material, material_status: 'APPROVED_FOR_ANALYSIS' })
  })

  it('lists recognized knowledge materials and approves the selected revision', async () => {
    const wrapper = mount(KnowledgeReviewView, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    expect(apiMocks.listKnowledgeMaterials).toHaveBeenCalledWith({
      product_id: 'PRODUCT-ONE', material_status: 'RECOGNIZED', size: 100,
    })
    expect(wrapper.text()).toContain('积木商品知识补充')
    await wrapper.get('.text-button').trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('机关山洞场景积木')

    await wrapper.get('input').setValue('R006.1正式验收')
    await wrapper.get('textarea').setValue('已核对来源与商品范围')
    await wrapper.findAll('.actions .button')[0].trigger('click')
    await flushPromises()

    expect(apiMocks.reviewKnowledgeMaterial).toHaveBeenCalledWith('KMT-ONE', {
      revision: 1,
      decision: 'APPROVE_FOR_ANALYSIS',
      reviewed_by: 'R006.1正式验收',
      review_note: '已核对来源与商品范围',
    })
    expect(wrapper.text()).toContain('资料已审核通过')
  })
})
