import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import KnowledgeMaterialsView from '../src/views/KnowledgeMaterialsView.vue'
import { getKnowledgeMaterial, listKnowledgeMaterials } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  apiErrorMessage: vi.fn(() => '资料服务暂时不可用'),
  getKnowledgeMaterial: vi.fn(),
  listKnowledgeMaterials: vi.fn(),
  reviewKnowledgeMaterial: vi.fn(),
  uploadKnowledgeMaterial: vi.fn(),
}))

const mockedList = vi.mocked(listKnowledgeMaterials)
const mockedDetail = vi.mocked(getKnowledgeMaterial)

const material = {
  material_id: 'KMT-TEST-1', revision: 1, store_code: 'STORE-ONE', product_id: 'PRODUCT-ONE', sku_id: null,
  material_type: 'PRODUCT_SPEC' as const, display_name: '积木规格说明', original_filename: 'spec.txt',
  content_hash: 'sha256:test', redaction_version: 'v1-reminder-only', material_status: 'RECOGNIZED' as const,
  recognition_summary: { readable: true, file_extension: '.txt', detected_fields: ['适用年龄'], missing_expected_fields: ['包装清单'], privacy_reminder: '请确认不包含客户隐私。' },
  submitted_by: '运营测试', reviewed_by: null, reviewed_at: null, review_note: null,
  created_at: '2026-07-28T00:00:00Z', updated_at: '2026-07-28T00:00:00Z',
}

describe('KnowledgeMaterialsView', () => {
  beforeEach(() => {
    mockedList.mockReset()
    mockedDetail.mockReset()
    mockedList.mockResolvedValue({ items: [material], total: 1, page: 1, size: 20 })
    mockedDetail.mockResolvedValue({ ...material, analysis_text_preview: '适用年龄：6-12岁。' })
  })

  it('shows the Chinese controlled upload workflow and never advertises automatic publication', async () => {
    const wrapper = mount(KnowledgeMaterialsView, { global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } } })
    await flushPromises()

    expect(wrapper.text()).toContain('商品资料上传与审核')
    expect(wrapper.text()).toContain('下载资料模板')
    expect(wrapper.text()).toContain('不会自动发布')
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
