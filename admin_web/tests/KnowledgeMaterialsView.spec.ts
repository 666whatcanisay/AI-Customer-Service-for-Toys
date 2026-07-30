import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import KnowledgeMaterialsView from '../src/views/KnowledgeMaterialsView.vue'

const apiMocks = vi.hoisted(() => ({
  apiErrorMessage: vi.fn(() => '资料服务暂时不可用'),
  getProductKnowledgeImportMergePreview: vi.fn(),
  getProductKnowledgeImportPreflight: vi.fn(),
  listOperationStores: vi.fn(),
  reviewProductKnowledgeImport: vi.fn(),
  uploadProductKnowledgeImport: vi.fn(),
}))

vi.mock('vue-router', () => ({ useRoute: () => ({ query: {} }) }))
vi.mock('../src/api/client', () => apiMocks)

const preflight = {
  batch_id: 'batch-r009-1',
  status: 'IDENTIFIED_PENDING_REVIEW',
  can_review: true,
  file_result: { filename: '商品知识采集模板V1.xlsx', valid: true },
  sheet_results: ['填写说明', '数据填写', '示例数据', '字段说明'].map((sheet_name) => ({
    sheet_name, present: true, visible: true, valid: true, errors: [],
  })),
  field_validation_result: { valid: true, data_row_count: 1, blocking_issue_count: 0, issues: [] },
  product_identification_result: { total_products: 1, new_count: 1, existing_count: 0, conflict_count: 0 },
}

const mergePreview = {
  batch_id: 'batch-r009-1',
  status: 'IDENTIFIED_PENDING_REVIEW',
  page: 1,
  page_size: 200,
  total: 1,
  items: [{
    product: {
      change_set_id: 'change-1',
      product_name: '积木小屋',
      target_product_id: null,
      operation: 'CREATE',
      status: 'IDENTIFIED_PENDING_REVIEW',
      base_snapshot_hash: 'a'.repeat(64),
      version: 1,
    },
    fields: [{
      field_key: 'product_knowledge.product_summary',
      field_label: '商品简介',
      old_value: null,
      incoming_value: '儿童拼装积木玩具。',
      merged_value: '儿童拼装积木玩具。',
      change_type: 'ADD',
    }],
  }],
}

describe('KnowledgeMaterialsView R009', () => {
  beforeEach(() => {
    sessionStorage.clear()
    vi.clearAllMocks()
    vi.stubGlobal('alert', vi.fn())
    apiMocks.listOperationStores.mockResolvedValue({
      items: [{
        store_ref: 7,
        store_name: '玩趣乐园积木店-拼多多',
        platform_name: '拼多多',
        status: 'ACTIVE',
        status_name: '正常',
        product_count: 0,
        created_at: '2026-07-30T00:00:00Z',
        remarks: '',
      }],
      total: 1,
    })
    apiMocks.uploadProductKnowledgeImport.mockResolvedValue({
      batch_id: 'batch-r009-1',
      status: 'IDENTIFIED_PENDING_REVIEW',
    })
    apiMocks.getProductKnowledgeImportPreflight.mockResolvedValue(preflight)
    apiMocks.getProductKnowledgeImportMergePreview.mockResolvedValue(mergePreview)
    apiMocks.reviewProductKnowledgeImport.mockResolvedValue({
      receipt_id: 'receipt-1',
      batch_id: 'batch-r009-1',
      change_set_id: 'change-1',
      decision: 'APPROVE',
      outcome: 'APPLIED',
      reviewed_by: '知识运营',
      reviewed_at: '2026-07-30T00:00:00Z',
      applied_product_id: 'product-1',
      applied_field_count: 1,
      before_snapshot_hash: 'a'.repeat(64),
      after_snapshot_hash: 'b'.repeat(64),
    })
  })

  it('shows the three-step fixed-template workflow and marks five templates as developing', async () => {
    const wrapper = mount(KnowledgeMaterialsView, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('Step 1 · 目标业务店铺')
    expect(wrapper.text()).toContain('Step 2 · 导入模板类型')
    expect(wrapper.text()).toContain('Step 3 · 商品知识 Excel')
    expect(wrapper.text()).toContain('商品知识采集模板 · 已支持')
    expect(wrapper.text().match(/开发中/g)).toHaveLength(5)
    expect(wrapper.text()).toContain('不调用 AI')
    expect(wrapper.text()).toContain('审核前正式数据零写入')

    const templateSelect = wrapper.findAll('select')[1]
    await templateSelect.setValue('FAQ')
    expect(window.alert).toHaveBeenCalledWith('该模板导入功能暂未开放')
    expect(wrapper.text()).toContain('该模板导入功能暂未开放')
  })

  it('uploads the supported workbook, renders field merge values, and submits approval', async () => {
    const wrapper = mount(KnowledgeMaterialsView, {
      global: { stubs: { RouterLink: { template: '<a><slot /></a>' } } },
    })
    await flushPromises()

    await wrapper.findAll('select')[0].setValue('7')
    await wrapper.get('input[placeholder="填写运营人员姓名或账号"]').setValue('知识运营')
    const fileInput = wrapper.get('input[type="file"]')
    const file = new File(['workbook'], '商品知识采集模板V1.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    })
    Object.defineProperty(fileInput.element, 'files', { configurable: true, value: [file] })
    await fileInput.trigger('change')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(apiMocks.uploadProductKnowledgeImport).toHaveBeenCalledWith(
      file,
      { store_ref: 7, template_type: 'PRODUCT_KNOWLEDGE', operator: '知识运营' },
      expect.stringContaining('product-knowledge-upload-'),
    )
    expect(wrapper.text()).toContain('文件预检结果')
    expect(wrapper.text()).toContain('积木小屋')
    expect(wrapper.text()).toContain('商品简介')
    expect(wrapper.text()).toContain('儿童拼装积木玩具。')
    expect(wrapper.text()).toContain('新增')
    expect(wrapper.text()).toContain('已识别待审核')

    await wrapper.get('.review-actions .button').trigger('click')
    await flushPromises()
    expect(apiMocks.reviewProductKnowledgeImport).toHaveBeenCalledWith(
      'batch-r009-1',
      'change-1',
      expect.objectContaining({
        decision: 'APPROVE',
        operator: '知识运营',
        expected_base_snapshot_hash: 'a'.repeat(64),
        expected_change_set_version: 1,
      }),
      expect.stringContaining('product-knowledge-approve-'),
    )
    expect(wrapper.text()).toContain('已审核通过并完成字段级 Merge')
  })
})
