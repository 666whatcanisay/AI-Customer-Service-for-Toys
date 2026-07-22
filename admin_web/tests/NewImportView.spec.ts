import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import NewImportView from '../src/views/NewImportView.vue'
import { preflightProductSku, uploadProductSku } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  preflightProductSku: vi.fn(),
  uploadProductSku: vi.fn(),
  productSkuTemplateUrl: vi.fn(() => '/template.xlsx'),
  apiErrorMessage: vi.fn(() => '请求失败'),
}))

const mockedPreflight = vi.mocked(preflightProductSku)
const mockedUpload = vi.mocked(uploadProductSku)
const routerLink = { props: ['to'], template: '<a><slot /></a>' }

function preflight(canImport = true) {
  return {
    original_filename: 'products.xlsx',
    file_sha256: 'a'.repeat(64),
    file_size_bytes: 1024,
    worksheets: ['商品SKU资料', '填写说明'],
    data_row_count: 10,
    valid_rows: canImport ? 10 : 9,
    invalid_rows: canImport ? 0 : 1,
    duplicate_rows: 0,
    conflict_rows: 0,
    missing_columns: canImport ? [] : ['product_name'],
    unknown_columns: [],
    formula_cell_count: 0,
    hidden_sheet_warnings: [],
    blank_row_count: 1,
    error_summary: canImport
      ? []
      : [{ code: 'INVALID_TEMPLATE', count: 1, message: 'Required column is missing' }],
    warning_summary: [
      { code: 'BLANK_ROWS_IGNORED', count: 1, message: 'Blank rows are ignored' },
    ],
    can_import: canImport,
  }
}

function batch() {
  return {
    id: 'batch-1',
    batch_id: 'batch-1',
    tenant_id: 'tenant-demo',
    import_type: 'PRODUCT_SKU',
    original_filename: 'demo.xlsx',
    file_sha256: 'hash',
    status: 'READY_FOR_REVIEW' as const,
    total_rows: 10,
    valid_rows: 10,
    invalid_rows: 0,
    duplicate_rows: 0,
    created_at: '2026-07-22T00:00:00Z',
    completed_at: '2026-07-22T00:00:01Z',
    created_by: 'test',
    error_message: null,
  }
}

function mountView() {
  return mount(NewImportView, { global: { stubs: { RouterLink: routerLink } } })
}

async function chooseFile(wrapper: ReturnType<typeof mount>, file: File): Promise<void> {
  const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
}

async function chooseXlsx(wrapper: ReturnType<typeof mount>): Promise<void> {
  await chooseFile(
    wrapper,
    new File(['xlsx'], 'products.xlsx', {
      type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    }),
  )
}

async function runSuccessfulPreflight(wrapper: ReturnType<typeof mount>): Promise<void> {
  mockedPreflight.mockResolvedValue(preflight(true))
  await wrapper.get('[data-testid="preflight-button"]').trigger('click')
  await flushPromises()
}

describe('NewImportView', () => {
  beforeEach(() => {
    mockedPreflight.mockReset()
    mockedUpload.mockReset()
  })

  it('rejects non-xlsx files before preflight or upload', async () => {
    const wrapper = mountView()
    await chooseFile(wrapper, new File(['bad'], 'products.csv', { type: 'text/csv' }))

    expect(wrapper.text()).toContain('仅支持 .xlsx 文件')
    expect(mockedPreflight).not.toHaveBeenCalled()
    expect(mockedUpload).not.toHaveBeenCalled()
  })

  it('shows a successful preflight summary and enables formal upload', async () => {
    const wrapper = mountView()
    await chooseXlsx(wrapper)

    expect(wrapper.get('[data-testid="upload-button"]').attributes()).toHaveProperty('disabled')
    await runSuccessfulPreflight(wrapper)

    expect(wrapper.text()).toContain('预检通过')
    expect(wrapper.text()).toContain('BLANK_ROWS_IGNORED')
    expect(wrapper.text()).toContain('商品SKU资料')
    expect(wrapper.get('[data-testid="upload-button"]').attributes()).not.toHaveProperty('disabled')
  })

  it('shows a preflight request failure and keeps formal upload disabled', async () => {
    mockedPreflight.mockRejectedValue(new Error('offline'))
    const wrapper = mountView()
    await chooseXlsx(wrapper)

    await wrapper.get('[data-testid="preflight-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('请求失败')
    expect(wrapper.get('[data-testid="upload-button"]').attributes()).toHaveProperty('disabled')
    expect(mockedUpload).not.toHaveBeenCalled()
  })

  it('uses can_import=false to block formal upload and show errors', async () => {
    mockedPreflight.mockResolvedValue(preflight(false))
    const wrapper = mountView()
    await chooseXlsx(wrapper)

    await wrapper.get('[data-testid="preflight-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('预检未通过')
    expect(wrapper.text()).toContain('INVALID_TEMPLATE')
    expect(wrapper.text()).toContain('product_name')
    expect(wrapper.get('[data-testid="upload-button"]').attributes()).toHaveProperty('disabled')
  })

  it('uploads only after a passing preflight and shows the result', async () => {
    const wrapper = mountView()
    await chooseXlsx(wrapper)
    await runSuccessfulPreflight(wrapper)
    mockedUpload.mockResolvedValue(batch())

    await wrapper.get('[data-testid="upload-button"]').trigger('click')
    await flushPromises()

    expect(mockedUpload).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('READY_FOR_REVIEW')
    expect(wrapper.text()).toContain('待审核有效行')
  })

  it('shows upload progress after a passing preflight', async () => {
    let finish!: (value: ReturnType<typeof batch>) => void
    const wrapper = mountView()
    await chooseXlsx(wrapper)
    await runSuccessfulPreflight(wrapper)
    mockedUpload.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve
      }),
    )

    await wrapper.get('[data-testid="upload-button"]').trigger('click')
    expect(wrapper.text()).toContain('上传中')
    finish(batch())
    await flushPromises()
  })

  it('shows an upload error after a passing preflight', async () => {
    const wrapper = mountView()
    await chooseXlsx(wrapper)
    await runSuccessfulPreflight(wrapper)
    mockedUpload.mockRejectedValue(new Error('server rejected'))

    await wrapper.get('[data-testid="upload-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('请求失败')
  })

  it('exposes the standard template download', () => {
    const wrapper = mountView()
    const link = wrapper.get('a[download]')

    expect(link.attributes('href')).toBe('/template.xlsx')
    expect(link.text()).toContain('下载标准 Excel 模板')
  })
})
