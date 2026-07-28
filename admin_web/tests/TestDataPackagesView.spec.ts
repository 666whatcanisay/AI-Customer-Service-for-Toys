import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import TestDataPackagesView from '../src/views/TestDataPackagesView.vue'
import {
  importTestDataPackage,
  listTestDataPackages,
  preflightTestDataPackage,
} from '../src/api/client'

vi.mock('../src/api/client', () => ({
  listTestDataPackages: vi.fn(),
  preflightTestDataPackage: vi.fn(),
  importTestDataPackage: vi.fn(),
  apiErrorMessage: vi.fn(() => '测试包请求失败'),
}))

const mockedList = vi.mocked(listTestDataPackages)
const mockedPreflight = vi.mocked(preflightTestDataPackage)
const mockedImport = vi.mocked(importTestDataPackage)

function counts() {
  return {
    products: 5,
    skus_and_bundles: 18,
    image_evidence: 35,
    source_records_total: 37,
    faqs: 16,
    safety_rules: 8,
    evaluation_cases: 28,
    issues: 13,
  }
}

function summary() {
  return {
    package_id: 'PDD-SM-2026-001-TEST',
    package_name: '汕明测试基线',
    version: 'V0.3.1',
    schema_version: '0.3.1-test',
    tenant_id: 'TENANT-PDD-SM-TEST',
    platform: 'pdd',
    store_code: 'PDD-SM',
    test_data_mode: true,
    production_usable: false,
    response_mode: 'SUGGESTION_ONLY',
    allow_auto_send: false,
    import_status: 'IMPORTED_TEST_ONLY',
    original_filename: 'test.zip',
    zip_sha256: 'a'.repeat(64),
    counts: counts(),
    imported_at: '2026-07-22T00:00:00Z',
  }
}

function preflight(canImport = true) {
  return {
    original_filename: 'test.zip',
    file_sha256: 'a'.repeat(64),
    file_size_bytes: 1000,
    package_id: 'PDD-SM-2026-001-TEST',
    package_name: '汕明测试基线',
    version: 'V0.3.1',
    schema_version: '0.3.1-test',
    tenant_id: 'TENANT-PDD-SM-TEST',
    platform: 'pdd',
    store_code: 'PDD-SM',
    test_data_mode: true,
    production_usable: false,
    response_mode: 'SUGGESTION_ONLY',
    allow_auto_send: false,
    worksheets: ['00_版本与试点范围', '08_冲突与待确认事项'],
    counts: counts(),
    warnings: [{ code: 'TEST_ONLY_PACKAGE', message: '测试专用' }],
    errors: canImport ? [] : [{ code: 'BLOCKED', message: '预检失败' }],
    can_import: canImport,
  }
}

async function chooseZip(wrapper: ReturnType<typeof mount>): Promise<void> {
  const input = wrapper.get('input[type="file"]')
  const file = new File(['zip'], 'shanming-v0.3.1.zip', { type: 'application/zip' })
  Object.defineProperty(input.element, 'files', { value: [file], configurable: true })
  await input.trigger('change')
}

describe('TestDataPackagesView', () => {
  beforeEach(() => {
    mockedList.mockReset()
    mockedPreflight.mockReset()
    mockedImport.mockReset()
    mockedList.mockResolvedValue({ items: [], total: 0 })
  })

  it('shows imported counts and explicit test-only restrictions', async () => {
    mockedList.mockResolvedValue({ items: [summary()], total: 1 })
    const wrapper = mount(TestDataPackagesView)
    await flushPromises()

    expect(wrapper.text()).toContain('PDD-SM-2026-001-TEST')
    expect(wrapper.text()).toContain('已导入（仅测试）')
    expect(wrapper.text()).toContain('测试专用 / 不可生产 / 禁止自动发送')
    expect(wrapper.text()).toContain('28')
  })

  it('rejects non-ZIP files before preflight', async () => {
    const wrapper = mount(TestDataPackagesView)
    await flushPromises()
    const input = wrapper.get('input[type="file"]')
    Object.defineProperty(input.element, 'files', {
      value: [new File(['bad'], 'package.xlsx')],
      configurable: true,
    })
    await input.trigger('change')

    expect(wrapper.text()).toContain('仅支持 V0.3.1 测试数据包 ZIP')
    expect(mockedPreflight).not.toHaveBeenCalled()
  })

  it('keeps import disabled when preflight request fails', async () => {
    mockedPreflight.mockRejectedValue(new Error('invalid manifest'))
    const wrapper = mount(TestDataPackagesView)
    await flushPromises()
    await chooseZip(wrapper)
    await wrapper.get('[data-testid="package-preflight"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('测试包请求失败')
    expect(wrapper.get('[data-testid="package-import"]').attributes()).toHaveProperty('disabled')
  })

  it('uses can_import=false as a hard import gate', async () => {
    mockedPreflight.mockResolvedValue(preflight(false))
    const wrapper = mount(TestDataPackagesView)
    await flushPromises()
    await chooseZip(wrapper)
    await wrapper.get('[data-testid="package-preflight"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('识别结果：ZIP 预检未通过')
    expect(wrapper.get('[data-testid="package-import"]').attributes()).toHaveProperty('disabled')
    expect(mockedImport).not.toHaveBeenCalled()
  })

  it('preflights successfully, enables import, and renders exact counts', async () => {
    mockedPreflight.mockResolvedValue(preflight(true))
    mockedImport.mockResolvedValue(summary())
    const wrapper = mount(TestDataPackagesView)
    await flushPromises()
    await chooseZip(wrapper)
    await wrapper.get('[data-testid="package-preflight"]').trigger('click')
    await flushPromises()

    expect(wrapper.text()).toContain('识别结果：ZIP 预检通过')
    expect(wrapper.text()).toContain('TEST_ONLY_PACKAGE')
    expect(wrapper.get('[data-testid="package-import"]').attributes()).not.toHaveProperty('disabled')

    await wrapper.get('[data-testid="package-import"]').trigger('click')
    await flushPromises()
    expect(mockedImport).toHaveBeenCalledTimes(1)
    expect(wrapper.text()).toContain('已导入（仅测试）')
  })
})
