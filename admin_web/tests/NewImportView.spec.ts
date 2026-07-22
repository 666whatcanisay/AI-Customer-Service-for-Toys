import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'

import NewImportView from '../src/views/NewImportView.vue'
import { uploadProductSku } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  uploadProductSku: vi.fn(),
  productSkuTemplateUrl: vi.fn(() => '/template.xlsx'),
  apiErrorMessage: vi.fn(() => '上传失败'),
}))

const mockedUpload = vi.mocked(uploadProductSku)
const routerLink = { props: ['to'], template: '<a><slot /></a>' }

function batch() {
  return {
    id: 'batch-1',
    batch_id: 'batch-1',
    tenant_id: 'tenant-demo',
    import_type: 'PRODUCT_SKU',
    original_filename: 'demo.xlsx',
    file_sha256: 'hash',
    status: 'READY_FOR_REVIEW' as const,
    total_rows: 12,
    valid_rows: 8,
    invalid_rows: 2,
    duplicate_rows: 2,
    created_at: '2026-07-22T00:00:00Z',
    completed_at: '2026-07-22T00:00:01Z',
    created_by: 'test',
    error_message: null,
  }
}

async function chooseFile(wrapper: ReturnType<typeof mount>, file: File): Promise<void> {
  const input = wrapper.get('input[type="file"]')
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
}

describe('NewImportView', () => {
  it('rejects non-xlsx files before upload', async () => {
    const wrapper = mount(NewImportView, { global: { stubs: { RouterLink: routerLink } } })
    await chooseFile(wrapper, new File(['bad'], 'products.csv', { type: 'text/csv' }))

    expect(wrapper.text()).toContain('仅支持 .xlsx 文件')
    expect(mockedUpload).not.toHaveBeenCalled()
  })

  it('shows upload state and then a real result summary', async () => {
    let finish!: (value: ReturnType<typeof batch>) => void
    mockedUpload.mockReturnValue(
      new Promise((resolve) => {
        finish = resolve
      }),
    )
    const wrapper = mount(NewImportView, { global: { stubs: { RouterLink: routerLink } } })
    await chooseFile(
      wrapper,
      new File(['xlsx'], 'products.xlsx', {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      }),
    )
    await wrapper.get('button').trigger('click')
    expect(wrapper.text()).toContain('上传中')

    finish(batch())
    await flushPromises()
    expect(wrapper.text()).toContain('READY_FOR_REVIEW')
    expect(wrapper.text()).toContain('待审核有效行')
    expect(wrapper.text()).toContain('8')
  })

  it('shows an API error summary', async () => {
    mockedUpload.mockRejectedValue(new Error('server rejected'))
    const wrapper = mount(NewImportView, { global: { stubs: { RouterLink: routerLink } } })
    await chooseFile(
      wrapper,
      new File(['xlsx'], 'products.xlsx', {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      }),
    )
    await wrapper.get('button').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('上传失败')
  })

  it('exposes the standard template download', () => {
    const wrapper = mount(NewImportView, { global: { stubs: { RouterLink: routerLink } } })
    const link = wrapper.get('a[download]')

    expect(link.attributes('href')).toBe('/template.xlsx')
    expect(link.text()).toContain('下载标准 Excel 模板')
  })
})
