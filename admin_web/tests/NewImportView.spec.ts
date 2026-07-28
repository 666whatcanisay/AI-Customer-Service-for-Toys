import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import NewImportView from '../src/views/NewImportView.vue'
import { preflightProductSku, uploadProductSku, type ProductSkuPreflight } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  preflightProductSku: vi.fn(), uploadProductSku: vi.fn(), productSkuTemplateUrl: vi.fn(() => '/template.xlsx'), apiErrorMessage: vi.fn(() => '请求失败'),
}))

const mockedPreflight = vi.mocked(preflightProductSku)
const mockedUpload = vi.mocked(uploadProductSku)
const routerLink = { props: ['to'], template: '<a><slot /></a>' }

function preflight(canImport = true): ProductSkuPreflight {
  return {
    original_filename: 'products.xlsx', file_sha256: 'a'.repeat(64), file_size_bytes: 1024, worksheets: ['商品SKU资料', '填写说明'], data_row_count: 10,
    recognized_product_count: 3, recognized_sku_count: 10, rows_needing_manual_completion: canImport ? 0 : 1, missing_field_counts: canImport ? {} as Record<string, number> : { product_name: 1 },
    valid_rows: canImport ? 10 : 9, invalid_rows: canImport ? 0 : 1, duplicate_rows: 0, conflict_rows: 0, missing_columns: [], unknown_columns: [], formula_cell_count: 0, hidden_sheet_warnings: [], blank_row_count: 1,
    error_summary: canImport ? [] : [{ code: 'REQUIRED_FIELD_MISSING', count: 1, message: 'ignored raw message' }], warning_summary: [{ code: 'BLANK_ROWS_IGNORED', count: 1, message: 'ignored raw message' }], can_import: canImport,
  }
}
function batch() { return { id: 'batch-1', batch_id: 'batch-1', tenant_id: 'tenant-demo', target_store_code: null, import_type: 'PRODUCT_SKU', original_filename: 'demo.xlsx', file_sha256: 'hash', status: 'READY_FOR_REVIEW' as const, total_rows: 10, valid_rows: 10, invalid_rows: 0, duplicate_rows: 0, created_at: '2026-07-22T00:00:00Z', completed_at: '2026-07-22T00:00:01Z', created_by: 'test', error_message: null } }
function mountView() { return mount(NewImportView, { global: { stubs: { RouterLink: routerLink } } }) }
async function chooseFile(wrapper: ReturnType<typeof mount>, file: File): Promise<void> { const input = wrapper.get('input[type="file"]'); Object.defineProperty(input.element, 'files', { value: [file], configurable: true }); await input.trigger('change') }
async function chooseXlsx(wrapper: ReturnType<typeof mount>): Promise<void> { await chooseFile(wrapper, new File(['xlsx'], 'products.xlsx', { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' })) }

describe('NewImportView', () => {
  beforeEach(() => { window.history.replaceState({}, '', '/'); mockedPreflight.mockReset(); mockedUpload.mockReset() })

  it('explains the novice import flow and exposes the standard template', () => {
    const wrapper = mountView()
    expect(wrapper.text()).toContain('先准备这些数据')
    expect(wrapper.text()).toContain('第一步：下载模板')
    expect(wrapper.text()).toContain('第 3 步：上传并预检')
    expect(wrapper.get('a[download]').attributes('href')).toBe('/template.xlsx')
  })

  it('rejects non-xlsx files before preflight', async () => {
    const wrapper = mountView(); await chooseFile(wrapper, new File(['bad'], 'products.csv', { type: 'text/csv' }))
    expect(wrapper.text()).toContain('仅支持 .xlsx 文件'); expect(mockedPreflight).not.toHaveBeenCalled()
  })

  it('renders server-recognized product, SKU, and manual completion counts', async () => {
    mockedPreflight.mockResolvedValue(preflight(false)); const wrapper = mountView(); await chooseXlsx(wrapper)
    await wrapper.get('[data-testid="preflight-button"]').trigger('click'); await flushPromises()
    expect(wrapper.text()).toContain('识别到商品'); expect(wrapper.text()).toContain('识别到 SKU'); expect(wrapper.text()).toContain('待人工补充'); expect(wrapper.text()).toContain('商品名称（1 行）'); expect(wrapper.text()).not.toContain('ignored raw message')
    expect(wrapper.get('[data-testid="upload-button"]').attributes()).toHaveProperty('disabled')
  })

  it('enables import only after a passing preflight', async () => {
    mockedPreflight.mockResolvedValue(preflight(true)); mockedUpload.mockResolvedValue(batch())
    const wrapper = mountView(); await chooseXlsx(wrapper); await wrapper.get('[data-testid="preflight-button"]').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-testid="upload-button"]').attributes()).not.toHaveProperty('disabled')
    await wrapper.get('[data-testid="upload-button"]').trigger('click'); await flushPromises()
    expect(mockedUpload).toHaveBeenCalledTimes(1); expect(wrapper.text()).toContain('导入完成')
  })
})
