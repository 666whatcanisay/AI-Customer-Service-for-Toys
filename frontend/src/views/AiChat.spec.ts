import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { PlatformClientError, RagClientError } from '@/api/errorMapper'
import type { RagAction, RagChatResult } from '@/api/ragTypes'
import AiChat from './AiChat.vue'

const LAST_STORE_KEY = 'mumu-customer-workbench:last-store'

const apiMocks = vi.hoisted(() => ({
  getRagHealth: vi.fn(),
  chat: vi.fn(),
  getPlatformHealth: vi.fn(),
  listStores: vi.fn(),
  listProducts: vi.fn(),
  listSkus: vi.fn()
}))

vi.mock('@/api/ragClient', () => ({
  ragClient: {
    getHealth: apiMocks.getRagHealth,
    chat: apiMocks.chat
  }
}))

vi.mock('@/api/platformClient', () => ({
  platformClient: {
    getHealth: apiMocks.getPlatformHealth,
    listStores: apiMocks.listStores,
    listProducts: apiMocks.listProducts,
    listSkus: apiMocks.listSkus
  }
}))

const store = {
  tenantId: 'TENANT-PDD-SM-TEST',
  platform: 'pdd',
  storeCode: 'PDD-SM',
  name: '汕明',
  trialEnabled: true,
  knowledgeScope: 'STORE_PRODUCT_SKU',
  responseMode: 'SUGGESTION_ONLY',
  allowAutoSend: false,
  testDataMode: true,
  productionUsable: false
}

const secondStore = { ...store, storeCode: 'PDD-SM-2', name: '汕明二店' }

const product = {
  productId: 'PROD-001',
  platform: 'pdd',
  storeCode: 'PDD-SM',
  officialName: '测试积木',
  displayName: '测试积木套装',
  salesStatus: 'ON_SALE',
  ageMin: 6,
  ageMax: 12,
  safetySummary: '仅用于测试。',
  reviewStatus: 'APPROVED',
  publishable: true
}

const secondProduct = { ...product, productId: 'PROD-002', displayName: '测试拼图' }
const secondStoreProducts = [
  { ...product, storeCode: 'PDD-SM-2' },
  { ...secondProduct, storeCode: 'PDD-SM-2' }
]

const sku = {
  skuId: 'SKU-RED',
  productId: 'PROD-001',
  skuCode: 'RED',
  officialName: '红色款',
  displayName: '红色款（测试）',
  relationType: 'CANONICAL',
  canonicalSkuId: null,
  referenceSkuId: null,
  componentSkuRefs: [],
  publishable: true
}

const resultFor = (action: RagAction = 'DIRECT_ANSWER', withSku = true): RagChatResult => ({
  requestId: 'req-ui-1',
  model: 'qwen-turbo',
  answer: action === 'ASK_CLARIFY'
    ? '请先确认客户咨询的具体款式。'
    : '建议回复：适用年龄请以商品包装标识为准。',
  action,
  riskLevel: action === 'TRANSFER_HUMAN' ? 'HIGH' : 'LOW',
  citations: [{
    file: 'toy-guide.pdf',
    page: 4,
    chunkId: 'chunk-4',
    summary: '包装标明适用年龄。',
    distance: 0.2,
    knowledgeVersion: 'v3',
    sourceIds: ['SRC-001'],
    productId: 'PROD-001',
    skuId: withSku ? 'SKU-RED' : null
  }],
  warnings: [],
  requiredFields: action === 'ASK_CLARIFY' ? ['sku_id'] : [],
  latencyMs: 95,
  context: {
    tenant_id: 'TENANT-PDD-SM-TEST',
    platform: 'pdd',
    store_code: 'PDD-SM',
    product_id: 'PROD-001',
    sku_id: withSku ? 'SKU-RED' : null
  }
})

const mountPage = () => mount(AiChat, {
  global: {
    plugins: [ElementPlus]
  }
})

const selectAt = async (wrapper: VueWrapper, index: number, value: string) => {
  const component = wrapper.findAllComponents({ name: 'ElSelect' })[index]
  if (!component) throw new Error(`Missing select ${index}`)
  component.vm.$emit('update:modelValue', value)
  component.vm.$emit('change', value)
  await flushPromises()
}

const selectContext = async (wrapper: VueWrapper, withSku = true) => {
  await selectAt(wrapper, 0, 'TENANT-PDD-SM-TEST::pdd::PDD-SM')
  await selectAt(wrapper, 1, 'PROD-001')
  if (withSku) await selectAt(wrapper, 2, 'SKU-RED')
}

const submit = async (wrapper: VueWrapper, withSku = true) => {
  await selectContext(wrapper, withSku)
  await wrapper.get('[data-testid="question-input"]').setValue('这个款式适合几岁？')
  await wrapper.get('[data-testid="submit-button"]').trigger('click')
  await flushPromises()
}

describe('AiChat B-T04 three-step workbench', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    apiMocks.getRagHealth.mockResolvedValue({ status: 'ok', ready: true })
    apiMocks.getPlatformHealth.mockResolvedValue({ status: 'ok', service: 'platform' })
    apiMocks.listStores.mockResolvedValue([store, secondStore])
    apiMocks.listProducts.mockImplementation((selectedStore) =>
      Promise.resolve(selectedStore.storeCode === 'PDD-SM-2'
        ? secondStoreProducts
        : [product, secondProduct])
    )
    apiMocks.listSkus.mockResolvedValue([sku])
    apiMocks.chat.mockResolvedValue(resultFor())
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockResolvedValue(undefined) }
    })
  })

  it('shows the three-step flow and cascades the platform/store, product, and SKU', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.get('[data-testid="safety-notice"]').text()).toContain(
      '当前为测试数据，仅供内部验证，禁止直接用于真实客户。'
    )
    expect(wrapper.text()).toContain('第 1 步')
    expect(wrapper.text()).toContain('第 2 步')
    expect(wrapper.text()).toContain('建议回复会显示在这里')

    await selectAt(wrapper, 0, 'TENANT-PDD-SM-TEST::pdd::PDD-SM')
    expect(apiMocks.listProducts).toHaveBeenCalledWith(store, expect.any(AbortSignal))
    await selectAt(wrapper, 1, 'PROD-001')
    expect(apiMocks.listSkus).toHaveBeenCalledWith(store, product, expect.any(AbortSignal))
  })

  it('remembers the last store and restores its product list', async () => {
    window.localStorage.setItem(LAST_STORE_KEY, 'TENANT-PDD-SM-TEST::pdd::PDD-SM')

    const wrapper = mountPage()
    await flushPromises()

    const selects = wrapper.findAllComponents({ name: 'ElSelect' })
    expect(selects[0]?.props('modelValue')).toBe('TENANT-PDD-SM-TEST::pdd::PDD-SM')
    expect(apiMocks.listProducts).toHaveBeenCalledWith(store, expect.any(AbortSignal))
  })

  it('clears product and SKU on store switch, and clears SKU on product switch', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await selectContext(wrapper)

    await selectAt(wrapper, 0, 'TENANT-PDD-SM-TEST::pdd::PDD-SM-2')
    let selects = wrapper.findAllComponents({ name: 'ElSelect' })
    expect(selects[1]?.props('modelValue')).toBe('')
    expect(selects[2]?.props('modelValue')).toBe('')
    expect(window.localStorage.getItem(LAST_STORE_KEY)).toBe(
      'TENANT-PDD-SM-TEST::pdd::PDD-SM-2'
    )

    await selectAt(wrapper, 1, 'PROD-001')
    await selectAt(wrapper, 2, 'SKU-RED')
    await selectAt(wrapper, 1, 'PROD-002')
    selects = wrapper.findAllComponents({ name: 'ElSelect' })
    expect(selects[2]?.props('modelValue')).toBe('')
  })

  it('explains that a product must be selected before generating', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await wrapper.get('[data-testid="question-input"]').setValue('这个商品适合几岁？')
    await wrapper.get('[data-testid="submit-button"]').trigger('click')

    expect(wrapper.get('[data-testid="request-error"]').text()).toContain(
      '尚未选择商品，请先完成第一步。'
    )
    expect(apiMocks.chat).not.toHaveBeenCalled()
  })

  it('sends the frozen context request and keeps sources folded by default', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await submit(wrapper)

    expect(apiMocks.chat).toHaveBeenCalledWith({
      question: '这个款式适合几岁？',
      context: {
        tenant_id: 'TENANT-PDD-SM-TEST',
        platform: 'pdd',
        store_code: 'PDD-SM',
        product_id: 'PROD-001',
        sku_id: 'SKU-RED'
      }
    }, expect.any(AbortSignal))
    expect(wrapper.get('[data-testid="action-tag"]').text()).toBe('可以直接参考')
    expect(wrapper.get('[data-testid="sources-details"]').attributes('open')).toBeUndefined()
    expect(wrapper.get('[data-testid="citation-item"]').text()).toContain('toy-guide.pdf')
  })

  it('keeps SKU optional and translates the clarification field into Chinese', async () => {
    apiMocks.chat.mockResolvedValue(resultFor('ASK_CLARIFY', false))
    const wrapper = mountPage()
    await flushPromises()
    await submit(wrapper, false)

    expect(apiMocks.chat.mock.calls[0]?.[0].context.sku_id).toBeNull()
    expect(wrapper.get('[data-testid="action-tag"]').text()).toBe('需要补充信息')
    expect(wrapper.get('[data-testid="required-fields"]').text()).toContain('具体款式（SKU）')
    expect(wrapper.get('[data-testid="required-fields"]').text()).not.toContain('sku_id')
  })

  it.each([
    ['DIRECT_ANSWER', '可以直接参考'],
    ['CONTROLLED_ANSWER', '请核对后使用'],
    ['ASK_CLARIFY', '需要补充信息'],
    ['REQUIRE_LOOKUP', '需要查询系统'],
    ['TRANSFER_HUMAN', '需要人工处理'],
    ['REFUSE', '不能作出该承诺']
  ] as const)('displays %s as %s', async (action, label) => {
    apiMocks.chat.mockResolvedValue(resultFor(action))
    const wrapper = mountPage()
    await flushPromises()
    await submit(wrapper)

    expect(wrapper.get('[data-testid="action-tag"]').text()).toBe(label)
    expect(wrapper.get('[data-testid="answer-card"]').text()).not.toContain(action)
  })

  it('keeps model, request, IDs, and retrieval details inside a closed technical section', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await submit(wrapper)

    const visibleAnswer = wrapper.get('[data-testid="answer-card"]').text()
    expect(visibleAnswer).not.toContain('req-ui-1')
    expect(visibleAnswer).not.toContain('qwen-turbo')
    expect(visibleAnswer).not.toContain('PROD-001')
    expect(visibleAnswer).not.toContain('DIRECT_ANSWER')
    expect(visibleAnswer).not.toContain('SRC-001')

    expect(wrapper.find('[data-testid="answer-technical-details"]').exists()).toBe(false)
    await wrapper.get('[data-testid="technical-toggle"]').trigger('click')
    const technical = wrapper.get('[data-testid="answer-technical-details"]')
    expect(technical.text()).toContain('req-ui-1')
    expect(technical.text()).toContain('qwen-turbo')
    expect(wrapper.get('[data-testid="citation-technical-details"]').text()).toContain('SRC-001')
  })

  it('copies the customer-service edit and records all three page-local outcomes', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await submit(wrapper)

    await wrapper.get('[data-testid="reply-draft"]').setValue('客服修改后的测试回复')
    await wrapper.get('[data-testid="copy-button"]').trigger('click')
    await flushPromises()
    expect(navigator.clipboard.writeText).toHaveBeenCalledWith('客服修改后的测试回复')

    await wrapper.get('[data-testid="direct-accept"]').trigger('click')
    expect(wrapper.get('[data-testid="adoption-result"]').text()).toContain('直接采用')
    await wrapper.get('[data-testid="edited-accept"]').trigger('click')
    expect(wrapper.get('[data-testid="adoption-result"]').text()).toContain('修改后采用')
    await wrapper.get('[data-testid="reject"]').trigger('click')
    expect(wrapper.get('[data-testid="adoption-result"]').text()).toContain('未采用')
  })

  it('shows an actionable data-service error separately from AI health', async () => {
    apiMocks.getPlatformHealth.mockRejectedValue(
      new PlatformClientError('unavailable', 'C 目录服务当前不可用', 503)
    )
    apiMocks.listStores.mockRejectedValue(
      new PlatformClientError('unavailable', 'C 目录接口尚未发布', 404)
    )
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.get('[data-testid="platform-error"]').text()).toContain(
      '数据服务不可用，请联系技术人员检查中台。'
    )
    expect(wrapper.get('[data-testid="system-summary"]').text()).toContain('系统正在连接')
  })

  it('shows actionable AI unavailable and timeout messages without Mock fallback', async () => {
    apiMocks.chat.mockRejectedValueOnce(
      new RagClientError('unavailable', 'RAG API 当前不可用，请稍后重试', 503)
    )
    const wrapper = mountPage()
    await flushPromises()
    await submit(wrapper)
    expect(wrapper.get('[data-testid="request-error"]').text()).toContain(
      'AI 服务不可用，请稍后重试或按原客服流程处理。'
    )

    apiMocks.chat.mockRejectedValueOnce(
      new RagClientError('timeout', '请求超时，请确认 RAG 服务状态后重试')
    )
    await wrapper.get('[data-testid="submit-button"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="request-error"]').text()).toContain(
      'AI 服务请求超时，请稍后重试或按原客服流程处理。'
    )
  })

  it('blocks duplicate submissions, shows the loading copy, and allows cancellation', async () => {
    apiMocks.chat.mockImplementation((_request, signal: AbortSignal) =>
      new Promise((_resolve, reject) => {
        signal.addEventListener('abort', () => reject(new Error('aborted')))
      })
    )
    const wrapper = mountPage()
    await flushPromises()
    await selectContext(wrapper)
    await wrapper.get('[data-testid="question-input"]').setValue('测试取消')
    await wrapper.get('[data-testid="submit-button"]').trigger('click')

    expect(wrapper.get('[data-testid="loading-state"]').text()).toContain(
      '正在查询商品资料并生成建议'
    )
    await wrapper.get('[data-testid="submit-button"]').trigger('click')
    expect(apiMocks.chat).toHaveBeenCalledTimes(1)

    await wrapper.get('[data-testid="cancel-button"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="request-error"]').text()).toContain('问答请求已取消')
  })
})
