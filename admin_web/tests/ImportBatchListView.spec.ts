import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import ImportBatchListView from '../src/views/ImportBatchListView.vue'
import { listImportBatches } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  listImportBatches: vi.fn(),
  apiErrorMessage: vi.fn(() => '批次接口错误'),
}))

const mockedList = vi.mocked(listImportBatches)
const routerLink = { props: ['to'], template: '<a><slot /></a>' }

describe('ImportBatchListView', () => {
  beforeEach(() => mockedList.mockReset())

  it('shows an explicit empty-batch state', async () => {
    mockedList.mockResolvedValue({ items: [], page: 1, page_size: 20, total: 0 })
    const wrapper = mount(ImportBatchListView, {
      global: { stubs: { RouterLink: routerLink } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('暂无导入批次')
  })

  it('renders only the batches returned by the API', async () => {
    mockedList.mockResolvedValue({
      page: 1,
      page_size: 20,
      total: 1,
      items: [{
        id: 'batch-1',
        batch_id: 'batch-1',
        tenant_id: 'tenant-demo',
        import_type: 'PRODUCT_SKU',
        original_filename: 'synthetic.xlsx',
        file_sha256: 'hash',
        status: 'READY_FOR_REVIEW',
        total_rows: 10,
        valid_rows: 8,
        invalid_rows: 1,
        duplicate_rows: 1,
        created_at: '2026-07-22T00:00:00Z',
        completed_at: '2026-07-22T00:00:01Z',
        created_by: 'test',
        error_message: null,
      }],
    })
    const wrapper = mount(ImportBatchListView, {
      global: { stubs: { RouterLink: routerLink } },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('batch-1')
    expect(wrapper.text()).toContain('synthetic.xlsx')
    expect(wrapper.text()).toContain('READY_FOR_REVIEW')
    expect(wrapper.findAll('tbody tr')).toHaveLength(1)
  })
})
