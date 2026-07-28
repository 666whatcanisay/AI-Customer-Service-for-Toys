import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import TestDataPackagesView from '../src/views/TestDataPackagesView.vue'
import { importTestDataPackage, listTestDataPackages, preflightTestDataPackage } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  listTestDataPackages: vi.fn(), preflightTestDataPackage: vi.fn(), importTestDataPackage: vi.fn(), productSkuTemplateUrl: vi.fn(() => '/template.xlsx'), apiErrorMessage: vi.fn(() => '测试包请求失败'),
}))

const mockedList = vi.mocked(listTestDataPackages)
const mockedPreflight = vi.mocked(preflightTestDataPackage)
const mockedImport = vi.mocked(importTestDataPackage)
const counts = () => ({ products: 5, skus_and_bundles: 18, image_evidence: 35, source_records_total: 37, faqs: 16, safety_rules: 8, evaluation_cases: 28, issues: 13 })
const summary = () => ({ package_id: 'PDD-SM-2026-001-TEST', package_name: '玩具测试基线', version: 'V0.3.1', schema_version: '0.3.1-test', tenant_id: 'TENANT-PDD-SM-TEST', platform: 'pdd', store_code: 'PDD-SM', test_data_mode: true, production_usable: false, response_mode: 'SUGGESTION_ONLY', allow_auto_send: false, import_status: 'IMPORTED_TEST_ONLY', original_filename: 'test.zip', zip_sha256: 'a'.repeat(64), counts: counts(), imported_at: '2026-07-22T00:00:00Z' })
const preflight = (canImport = true) => ({ original_filename: 'test.zip', file_sha256: 'a'.repeat(64), file_size_bytes: 1000, package_id: 'PDD-SM-2026-001-TEST', package_name: '玩具测试基线', version: 'V0.3.1', schema_version: '0.3.1-test', tenant_id: 'TENANT-PDD-SM-TEST', platform: 'pdd', store_code: 'PDD-SM', test_data_mode: true, production_usable: false, response_mode: 'SUGGESTION_ONLY', allow_auto_send: false, worksheets: ['版本与范围'], counts: counts(), warnings: [{ code: 'TEST_ONLY_PACKAGE', message: 'ignored raw message' }], errors: canImport ? [] : [{ code: 'BLOCKED', message: 'ignored raw message' }], can_import: canImport })
async function chooseZip(wrapper: ReturnType<typeof mount>): Promise<void> { const input = wrapper.get('input[type="file"]'); Object.defineProperty(input.element, 'files', { value: [new File(['zip'], 'test.zip', { type: 'application/zip' })], configurable: true }); await input.trigger('change') }

describe('TestDataPackagesView', () => {
  beforeEach(() => { window.history.replaceState({}, '', '/'); mockedList.mockReset(); mockedPreflight.mockReset(); mockedImport.mockReset(); mockedList.mockResolvedValue({ items: [], total: 0 }) })
  it('provides four downloads, Chinese explanations, and the four-step flow', async () => { const wrapper = mount(TestDataPackagesView); await flushPromises(); expect(wrapper.text()).toContain('商品与 SKU 模板'); expect(wrapper.text()).toContain('FAQ 模板'); expect(wrapper.text()).toContain('安全规则模板'); expect(wrapper.text()).toContain('来源证据模板'); expect(wrapper.text()).toContain('第四步：正式导入'); expect(wrapper.findAll('a[download]').length).toBe(5) })
  it('renders imported records with Chinese status and counts', async () => { mockedList.mockResolvedValue({ items: [summary()], total: 1 }); const wrapper = mount(TestDataPackagesView); await flushPromises(); expect(wrapper.text()).toContain('玩具测试基线'); expect(wrapper.text()).toContain('已导入（测试）'); expect(wrapper.text()).toContain('SKU数'); expect(wrapper.text()).toContain('仅测试 / 试运行') })
  it('uses preflight as a hard gate and converts warnings to Chinese', async () => { mockedPreflight.mockResolvedValue(preflight(true)); mockedImport.mockResolvedValue(summary()); const wrapper = mount(TestDataPackagesView); await flushPromises(); await chooseZip(wrapper); await wrapper.get('[data-testid="package-preflight"]').trigger('click'); await flushPromises(); expect(wrapper.text()).toContain('预检通过，可以导入'); expect(wrapper.text()).toContain('仅可用于测试 / 试运行环境'); expect(wrapper.text()).not.toContain('ignored raw message'); expect(wrapper.get('[data-testid="package-import"]').attributes()).not.toHaveProperty('disabled'); await wrapper.get('[data-testid="package-import"]').trigger('click'); await flushPromises(); expect(mockedImport).toHaveBeenCalledTimes(1) })
})
