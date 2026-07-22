import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ImportBatchDetailView from '../src/views/ImportBatchDetailView.vue'
import { getImportBatch, listImportRows } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  getImportBatch: vi.fn(),
  listImportRows: vi.fn(),
  errorReportUrl: vi.fn(() => '/errors.csv'),
  apiErrorMessage: vi.fn(() => '详情接口错误'),
}))

const mockedBatch = vi.mocked(getImportBatch)
const mockedRows = vi.mocked(listImportRows)
const routerLink = { props: ['to'], template: '<a><slot /></a>' }

describe('ImportBatchDetailView', () => {
  beforeEach(() => {
    mockedBatch.mockReset()
    mockedRows.mockReset()
  })

  it('shows batch details, row errors, and the error-report button', async () => {
    mockedBatch.mockResolvedValue({
      id: 'batch-1',
      batch_id: 'batch-1',
      tenant_id: 'tenant-demo',
      import_type: 'PRODUCT_SKU',
      original_filename: 'demo.xlsx',
      file_sha256: 'hash',
      status: 'READY_FOR_REVIEW',
      total_rows: 2,
      valid_rows: 1,
      invalid_rows: 1,
      duplicate_rows: 0,
      staged_rows: 1,
      created_at: '2026-07-22T00:00:00Z',
      completed_at: '2026-07-22T00:00:01Z',
      created_by: 'test',
      error_message: null,
    })
    mockedRows.mockResolvedValue({
      page: 1,
      page_size: 50,
      total: 1,
      items: [
        {
          id: 2,
          batch_id: 'batch-1',
          source_row_number: 4,
          raw_data: { product_name: '' },
          normalized_data: { product_name: null, sku_name: '演示 SKU' },
          row_hash: 'row-hash',
          validation_status: 'INVALID',
          warnings: [],
          errors: [
            {
              error_code: 'REQUIRED_FIELD_MISSING',
              message: 'missing',
              row_number: 4,
              field: 'product_name',
              raw_value: '',
              suggestion: '填写已核实的商品名',
            },
          ],
        },
      ],
    })
    const wrapper = mount(ImportBatchDetailView, {
      props: { batchId: 'batch-1' },
      global: { stubs: { RouterLink: routerLink } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('demo.xlsx')
    expect(wrapper.text()).toContain('REQUIRED_FIELD_MISSING')
    expect(wrapper.text()).toContain('填写已核实的商品名')
    expect(wrapper.get('a[download]').attributes('href')).toBe('/errors.csv')
  })

  it('shows an API error state', async () => {
    mockedBatch.mockRejectedValue(new Error('not found'))
    mockedRows.mockRejectedValue(new Error('not found'))
    const wrapper = mount(ImportBatchDetailView, {
      props: { batchId: 'missing' },
      global: { stubs: { RouterLink: routerLink } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('详情接口错误')
  })
})
