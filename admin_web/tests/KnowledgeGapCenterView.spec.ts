import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import KnowledgeGapCenterView from '../src/views/KnowledgeGapCenterView.vue'
import { getProductKnowledgeOverview, listProductKnowledgeGaps } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  apiErrorMessage: vi.fn(() => '暂时不可用'),
  getProductKnowledgeOverview: vi.fn(),
  listProductKnowledgeGaps: vi.fn(),
}))

describe('KnowledgeGapCenterView', () => {
  it('shows business names, priority and next action without technical identifiers', async () => {
    vi.mocked(getProductKnowledgeOverview).mockResolvedValue({ generated_at: '2026-07-29T00:00:00Z', has_data: true, stats: { store_count: 1, product_count: 1, ai_usable_product_count: 1, gap_count: 1, pending_review_count: 0 }, stores: [{ store_name: '木木小栈拼多多旗舰店', platform_name: '拼多多', product_count: 1, ai_usable_product_count: 1, gap_count: 1, pending_review_count: 0, technical_details: { store_code: 'STORE-ONE', platform: 'pinduoduo', product_id: null, product_code: null, sku_id: null, sku_code: null, source_id: null, material_id: null, revision: null, content_hash: null } }], boundary_note: '不代表发布。' })
    vi.mocked(listProductKnowledgeGaps).mockResolvedValue({ items: [{ store_name: '木木小栈拼多多旗舰店', product_name: 'Q66消防局积木', sku_name: '全部SKU', missing_topic: '适用年龄', occurrence_count: 6, impact_level: '高', priority: 'P1', workflow_status: 'PENDING', description: '当前资料没有年龄信息。', recommended_action: '补充并审核适用年龄资料。', safe_fallback: '当前资料未提供年龄信息，建议人工确认。' }], total: 1 })

    const wrapper = mount(KnowledgeGapCenterView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    expect(wrapper.text()).toContain('知识缺口中心')
    expect(wrapper.text()).toContain('木木小栈拼多多旗舰店 → Q66消防局积木 → 全部SKU')
    expect(wrapper.text()).toContain('P1')
    expect(wrapper.text()).toContain('补充并审核适用年龄资料')
    expect(wrapper.text()).not.toContain('product_id')
    expect(wrapper.text()).not.toContain('hash')
  })
})
