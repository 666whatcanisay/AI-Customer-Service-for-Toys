import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { PlatformClientError, RagClientError } from '@/api/errorMapper'
import type { RagAction, RagChatResult } from '@/api/ragTypes'
import {
  clearCustomerSessionActivity,
  useCustomerSessionActivity
} from '@/workspace/customerSessionActivity'
import { clearExperienceCaseSubmissions } from '@/workspace/experienceCaseSession'
import { CustomerIdentityKey } from '@/workspace/customerIdentity'
import AiChat from './AiChat.vue'

const LAST_STORE_KEY = 'mumu-customer-workbench:last-store'

const apiMocks = vi.hoisted(() => ({
  getRagHealth: vi.fn(),
  chat: vi.fn(),
  getPlatformHealth: vi.fn(),
  listStores: vi.fn(),
  listProducts: vi.fn(),
  listSkus: vi.fn(),
  submitExperienceCase: vi.fn(),
  submitAiFeedback: vi.fn(),
  createAiFeedbackIdempotencyKey: vi.fn(() => 'ai-feedback-test-key'),
  submitEfficiencyEvent: vi.fn(),
  createEfficiencyIdempotencyKey: vi.fn(() => 'customer-efficiency-test-key'),
  createInteractionId: vi.fn(() => 'interaction-test-1')
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

vi.mock('@/api/experienceCaseClient', () => ({
  experienceCaseClient: { submit: apiMocks.submitExperienceCase }
}))

vi.mock('@/api/aiResponseFeedbackClient', () => ({
  aiResponseFeedbackClient: { submit: apiMocks.submitAiFeedback },
  createAiResponseFeedbackIdempotencyKey: apiMocks.createAiFeedbackIdempotencyKey
}))

vi.mock('@/api/customerEfficiencyClient', () => ({
  customerEfficiencyClient: { submit: apiMocks.submitEfficiencyEvent },
  createCustomerEfficiencyIdempotencyKey: apiMocks.createEfficiencyIdempotencyKey,
  createCustomerInteractionId: apiMocks.createInteractionId,
  CustomerEfficiencyClientError: class CustomerEfficiencyClientError extends Error {}
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

const mountedPages: VueWrapper[] = []

const mountPage = () => {
  const wrapper = mount(AiChat, {
    global: {
      plugins: [ElementPlus],
      provide: {
        [CustomerIdentityKey as symbol]: {
          identity: ref({
            userId: 'CSU-ONE', displayName: '小木', role: 'CUSTOMER_SERVICE', status: 'ACTIVE',
            defaultStoreCode: 'PDD-SM', storeBindings: [
              { storeCode: 'PDD-SM', isDefault: true },
              { storeCode: 'PDD-SM-2', isDefault: false }
            ]
          }),
          clear: vi.fn()
        }
      }
    }
  })
  mountedPages.push(wrapper)
  return wrapper
}

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

const selectExperienceCaseFeedbackType = async (wrapper: VueWrapper, value: string) => {
  const selects = wrapper.findAllComponents({ name: 'ElSelect' })
  const feedbackSelect = selects.at(-1)
  if (!feedbackSelect) throw new Error('Missing experience-case feedback type selector')
  feedbackSelect.vm.$emit('update:modelValue', value)
  await flushPromises()
}

const selectAiFeedbackType = async (wrapper: VueWrapper, value: string) => {
  const reasonSelect = wrapper.findAllComponents({ name: 'ElSelect' })
    .find((component) => component.attributes('data-testid') === 'ai-feedback-type')
  if (!reasonSelect) throw new Error('Missing AI feedback type selector')
  reasonSelect.vm.$emit('update:modelValue', value)
  await flushPromises()
}

const submit = async (wrapper: VueWrapper, withSku = true) => {
  await selectContext(wrapper, withSku)
  await wrapper.get('[data-testid="question-input"]').setValue('这个款式适合几岁？')
  await wrapper.get('[data-testid="submit-button"]').trigger('click')
  await flushPromises()
}

describe('AiChat B-T04 three-step workbench', () => {
  afterEach(() => {
    mountedPages.splice(0).forEach((wrapper) => wrapper.unmount())
  })

  beforeEach(() => {
    vi.clearAllMocks()
    clearCustomerSessionActivity()
    clearExperienceCaseSubmissions()
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
    apiMocks.submitExperienceCase.mockResolvedValue({ caseId: 'CEC-001', reviewStatus: 'NEW' })
    apiMocks.submitAiFeedback.mockResolvedValue({
      feedbackId: 'ARF-001', status: 'NEW'
    })
    apiMocks.submitEfficiencyEvent.mockResolvedValue({ eventId: 'CEE-001', eventType: 'AI_REQUEST', accepted: true, createdAt: '2026-07-28T00:00:00Z' })
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
    expect(wrapper.get('[data-testid="customer-friendly-notice"]').text()).toContain('AI 辅助客服')
    expect(wrapper.get('[data-testid="customer-friendly-notice"]').text()).toContain('需要人工确认')
    expect(wrapper.get('[data-testid="customer-friendly-notice"]').text()).toContain('不自动发送')
    expect(wrapper.get('[data-testid="customer-friendly-notice"]').text()).toContain('不自动退款')
    expect(wrapper.get('[data-testid="customer-friendly-notice"]').text()).toContain('不修改订单')
    expect(wrapper.text()).toContain('第 1 步')
    expect(wrapper.text()).toContain('第 2 步')
    expect(wrapper.text()).toContain('建议回复会显示在这里')

    await selectAt(wrapper, 0, 'TENANT-PDD-SM-TEST::pdd::PDD-SM')
    expect(apiMocks.listProducts).toHaveBeenCalledWith(store, expect.any(AbortSignal))
    await selectAt(wrapper, 1, 'PROD-001')
    expect(apiMocks.listSkus).toHaveBeenCalledWith(store, product, expect.any(AbortSignal))
  })

  it('keeps version and runtime routing information folded into technical details', async () => {
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.find('[data-testid="runtime-details"]').exists()).toBe(false)
    const detailsButton = wrapper.find('[data-testid="system-summary"]').find('button')
    await detailsButton.trigger('click')

    expect(wrapper.get('[data-testid="runtime-details"]').text()).toContain('API')
    expect(wrapper.get('[data-testid="runtime-details"]').text()).toContain('Git')
  })

  it('remembers the last store and restores its product list', async () => {
    window.localStorage.setItem(LAST_STORE_KEY, 'TENANT-PDD-SM-TEST::pdd::PDD-SM')

    const wrapper = mountPage()
    await flushPromises()

    const selects = wrapper.findAllComponents({ name: 'ElSelect' })
    expect(selects[0]?.props('modelValue')).toBe('TENANT-PDD-SM-TEST::pdd::PDD-SM')
    expect(apiMocks.listProducts).toHaveBeenCalledWith(store, expect.any(AbortSignal))
  })

  it('loads the tester default store product list on a first visit', async () => {
    const wrapper = mountPage()
    await flushPromises()

    const selects = wrapper.findAllComponents({ name: 'ElSelect' })
    expect(selects[0]?.props('modelValue')).toBe('TENANT-PDD-SM-TEST::pdd::PDD-SM')
    expect(apiMocks.listProducts).toHaveBeenCalledWith(store, expect.any(AbortSignal))
  })

  it('keeps a no-product catalog state recoverable without allowing a context-free shortcut', async () => {
    apiMocks.listProducts.mockResolvedValue([])
    const wrapper = mountPage()
    await flushPromises()

    expect(wrapper.get('[data-testid="catalog-guidance"]').text()).toContain(
      '该店铺暂无可用于 AI 建议的商品'
    )
    expect(wrapper.get('[data-testid="catalog-refresh-button"]').text()).toContain('刷新商品目录')
    expect(wrapper.get('[data-testid="store-scope-note"]').text()).toContain('切换店铺会清空商品、SKU 和当前建议')
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
    expect(wrapper.get('[data-testid="action-tag"]').text()).toBe('🟢 可直接参考')
    expect(wrapper.get('[data-testid="sources-details"]').attributes('open')).toBeUndefined()
    expect(wrapper.get('[data-testid="citation-item"]').text()).toContain('toy-guide.pdf')
    expect(wrapper.get('[data-testid="context-summary"]').text()).toContain('当前店铺')
    expect(wrapper.get('[data-testid="context-summary"]').text()).toContain('商品上下文')
    expect(wrapper.get('[data-testid="context-summary"]').text()).toContain('SKU 上下文')
    expect(wrapper.get('[data-testid="answer-trust-note"]').text()).toContain('资料匹配，可参考')
    expect(wrapper.get('[data-testid="feedback-section"]').attributes('open')).toBeDefined()
    expect(useCustomerSessionActivity().aiAssists.value).toBe(1)
  })

  it('warns the agent when the answer has no verifiable knowledge source', async () => {
    apiMocks.chat.mockResolvedValue({ ...resultFor(), citations: [] })
    const wrapper = mountPage()
    await flushPromises()
    await submit(wrapper)

    expect(wrapper.get('[data-testid="no-knowledge-warning"]').text()).toContain(
      '未返回可核对的知识依据'
    )
    expect(wrapper.get('[data-testid="sources-details"]').text()).toContain('本次没有返回依据')
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
    ['DIRECT_ANSWER', '🟢 可直接参考'],
    ['CONTROLLED_ANSWER', '🟡 建议确认'],
    ['ASK_CLARIFY', '需要补充信息'],
    ['REQUIRE_LOOKUP', '需要查询系统'],
    ['TRANSFER_HUMAN', '🔴 建议人工处理'],
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

  it('keeps the core reply actions visible without changing the existing adoption flow', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await submit(wrapper)

    expect(wrapper.get('[data-testid="copy-button"]').text()).toContain('复制回复')
    expect(wrapper.get('[data-testid="edit-reply-button"]').text()).toContain('编辑回复')
    expect(wrapper.get('[data-testid="next-consultation-button"]').text()).toContain('处理下一条咨询')
    expect(wrapper.get('[data-testid="collect-experience-case-button"]').text()).toContain('收藏优秀案例')
    expect(wrapper.get('[data-testid="feedback-problem-button"]').text()).toContain('反馈问题')
    const focus = vi.spyOn(
      wrapper.get('[data-testid="reply-draft"]').element as HTMLTextAreaElement,
      'focus'
    )
    await wrapper.get('[data-testid="edit-reply-button"]').trigger('click')
    expect(focus).toHaveBeenCalled()
  })

  it('clears a stale answer when the next customer question changes while keeping product context', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await submit(wrapper)

    await wrapper.get('[data-testid="question-input"]').setValue('下一位客户想问库存')

    expect(wrapper.find('[data-testid="answer-card"]').exists()).toBe(false)
    expect(wrapper.get('[data-testid="next-question-notice"]').text()).toContain('已清空上一条建议')
    expect(wrapper.get('[data-testid="context-summary"]').text()).toContain('商品上下文')
  })

  it('starts the next consultation without discarding the selected store, product, or SKU', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await submit(wrapper)

    await wrapper.get('[data-testid="next-consultation-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.find('[data-testid="answer-card"]').exists()).toBe(false)
    expect((wrapper.get('[data-testid="question-input"]').element as HTMLTextAreaElement).value).toBe('')
    expect(wrapper.get('[data-testid="context-summary"]').text()).toContain('SKU 上下文')
  })

  it('enables experience capture or problem feedback only after the matching adoption decision', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await submit(wrapper)

    const collect = wrapper.get('[data-testid="collect-experience-case-button"]')
    const feedback = wrapper.get('[data-testid="feedback-problem-button"]')
    expect(wrapper.get('[data-testid="adoption-next-step"]').text()).toContain('先选择采用结果')
    expect(collect.attributes('disabled')).toBeDefined()
    expect(feedback.attributes('disabled')).toBeDefined()

    await wrapper.get('[data-testid="direct-accept"]').trigger('click')
    expect(collect.attributes('disabled')).toBeUndefined()
    expect(feedback.attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="adoption-next-step"]').text()).toContain('收藏为优秀案例')

    await wrapper.get('[data-testid="reject"]').trigger('click')
    expect(collect.attributes('disabled')).toBeDefined()
    expect(feedback.attributes('disabled')).toBeUndefined()
    expect(wrapper.get('[data-testid="adoption-next-step"]').text()).toContain('AI 问题反馈')
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

  it('keeps the edited reply available when browser clipboard access fails', async () => {
    Object.defineProperty(navigator, 'clipboard', {
      configurable: true,
      value: { writeText: vi.fn().mockRejectedValue(new Error('clipboard denied')) }
    })
    const wrapper = mountPage()
    await flushPromises()
    await submit(wrapper)

    await wrapper.get('[data-testid="reply-draft"]').setValue('保留给人工复制的回复')
    await wrapper.get('[data-testid="copy-button"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="copy-recovery-note"]').text()).toContain('浏览器未能自动复制')
    expect((wrapper.get('[data-testid="reply-draft"]').element as HTMLTextAreaElement).value).toBe(
      '保留给人工复制的回复'
    )
    expect(wrapper.get('[data-testid="copy-button"]').text()).toContain('复制回复')
  })

  it('submits a rejected answer to the independent AI feedback endpoint', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await submit(wrapper)

    await wrapper.get('[data-testid="reject"]').trigger('click')
    expect(wrapper.get('[data-testid="open-ai-feedback"]').text()).toContain('AI 问题反馈')
    expect(wrapper.get('[data-testid="save-experience-case"]').attributes('disabled')).toBeDefined()
    await wrapper.get('[data-testid="open-ai-feedback"]').trigger('click')
    expect(wrapper.get('[data-testid="ai-feedback-dialog"]').text()).toContain('为什么未采用？')
    await selectAiFeedbackType(wrapper, 'RISK_ISSUE')
    await wrapper.get('[data-testid="ai-feedback-submit"]').trigger('click')
    await flushPromises()

    expect(apiMocks.submitAiFeedback).toHaveBeenCalledWith({
      storeCode: 'PDD-SM', productId: 'PROD-001', skuId: 'SKU-RED', question: '这个款式适合几岁？',
      aiAnswer: '建议回复：适用年龄请以商品包装标识为准。', feedbackType: 'RISK_ISSUE',
      feedbackNote: null, finalAnswer: null, createdBy: 'CSU-ONE'
    }, expect.stringMatching(/^ai-feedback-/))
    expect(wrapper.get('[data-testid="ai-feedback-success"]').text()).toContain('反馈已记录。')
    expect(apiMocks.submitExperienceCase).not.toHaveBeenCalled()
    expect(useCustomerSessionActivity().feedbackSubmissions.value).toBe(1)
    expect(apiMocks.submitEfficiencyEvent).toHaveBeenCalledWith(expect.objectContaining({
      eventType: 'AI_REQUEST', operatorId: 'CSU-ONE', storeCode: 'PDD-SM', interactionId: 'interaction-test-1'
    }), 'customer-efficiency-test-key')
    expect(apiMocks.submitEfficiencyEvent).toHaveBeenCalledWith(expect.objectContaining({
      eventType: 'AI_REJECT', operatorId: 'CSU-ONE', interactionId: 'interaction-test-1'
    }), 'customer-efficiency-test-key')
    expect(apiMocks.submitEfficiencyEvent).toHaveBeenCalledWith(expect.objectContaining({
      eventType: 'AI_FEEDBACK_SUBMIT', operatorId: 'CSU-ONE', feedbackId: 'ARF-001'
    }), 'customer-efficiency-test-key')
  })

  it('reuses an in-flight feedback Idempotency-Key and displays C replay as the recorded result', async () => {
    apiMocks.submitAiFeedback
      .mockRejectedValueOnce(new Error('网络暂时不可用'))
      .mockResolvedValueOnce({ feedbackId: 'ARF-001', status: 'NEW' })
    const wrapper = mountPage()
    await flushPromises()
    await submit(wrapper)

    await wrapper.get('[data-testid="reject"]').trigger('click')
    await wrapper.get('[data-testid="open-ai-feedback"]').trigger('click')
    await selectAiFeedbackType(wrapper, 'FACT_ERROR')
    await wrapper.get('[data-testid="ai-feedback-submit"]').trigger('click')
    await flushPromises()
    const idempotencyKey = apiMocks.submitAiFeedback.mock.calls[0]?.[1]
    expect(wrapper.get('[data-testid="ai-feedback-error"]').text()).toContain('网络暂时不可用')

    await wrapper.get('[data-testid="ai-feedback-submit"]').trigger('click')
    await flushPromises()
    expect(apiMocks.submitAiFeedback).toHaveBeenCalledTimes(2)
    expect(apiMocks.submitAiFeedback.mock.calls[1]?.[1]).toBe(idempotencyKey)
    expect(wrapper.get('[data-testid="ai-feedback-success"]').text()).toContain('反馈已记录。')
  })

  it('requires an OTHER note and shows the feedback endpoint failure without a local success', async () => {
    apiMocks.submitAiFeedback.mockRejectedValue(new Error('AI 反馈接口尚未发布'))
    const wrapper = mountPage()
    await flushPromises()
    await submit(wrapper)

    await wrapper.get('[data-testid="reject"]').trigger('click')
    await wrapper.get('[data-testid="open-ai-feedback"]').trigger('click')
    await selectAiFeedbackType(wrapper, 'OTHER')
    await wrapper.get('[data-testid="ai-feedback-submit"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="ai-feedback-error"]').text()).toContain('选择“其他”时请填写')
    expect(apiMocks.submitAiFeedback).not.toHaveBeenCalled()

    await wrapper.get('[data-testid="ai-feedback-note"]').setValue('无法归类的测试问题')
    await wrapper.get('[data-testid="ai-feedback-submit"]').trigger('click')
    await flushPromises()
    expect(wrapper.get('[data-testid="ai-feedback-error"]').text()).toContain('反馈接口尚未发布')
    expect(wrapper.find('[data-testid="ai-feedback-success"]').exists()).toBe(false)
  })

  it('requires an explicit frozen experience type and shows the actual returned review status', async () => {
    const wrapper = mountPage()
    await flushPromises()
    await submit(wrapper)

    expect(wrapper.get('[data-testid="save-experience-case"]').attributes('disabled')).toBeDefined()
    expect(wrapper.get('[data-testid="save-experience-case"]').text()).toContain('收藏为优秀案例')
    expect(wrapper.text()).toContain('帮助系统持续优化')
    await wrapper.get('[data-testid="edited-accept"]').trigger('click')
    await wrapper.get('[data-testid="save-experience-case"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="experience-case-final-answer"]').setValue('客服审核后的测试回复')
    await wrapper.get('[data-testid="experience-case-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="experience-case-error"]').text()).toContain('请选择经验类型')
    expect(apiMocks.submitExperienceCase).not.toHaveBeenCalled()

    await selectExperienceCaseFeedbackType(wrapper, 'EDITED_ADOPTED')
    await wrapper.get('[data-testid="experience-case-submit"]').trigger('click')
    await flushPromises()

    expect(apiMocks.submitExperienceCase).toHaveBeenCalledWith({
      storeCode: 'PDD-SM', productId: 'PROD-001', skuId: 'SKU-RED', question: '这个款式适合几岁？',
      aiAnswer: '建议回复：适用年龄请以商品包装标识为准。', finalAnswer: '客服审核后的测试回复',
      feedbackType: 'EDITED_ADOPTED', createdBy: 'CSU-ONE'
    })
    expect(wrapper.get('[data-testid="experience-case-success"]').text()).toContain('新建')
  })

  it('shows the C endpoint failure and never records a local success', async () => {
    apiMocks.submitExperienceCase.mockRejectedValue(new Error('C 优秀案例接口尚未发布'))
    const wrapper = mountPage()
    await flushPromises()
    await submit(wrapper)
    await wrapper.get('[data-testid="direct-accept"]').trigger('click')
    await wrapper.get('[data-testid="save-experience-case"]').trigger('click')
    await flushPromises()
    await selectExperienceCaseFeedbackType(wrapper, 'ADOPTED')
    await wrapper.get('[data-testid="experience-case-submit"]').trigger('click')
    await flushPromises()

    expect(wrapper.get('[data-testid="experience-case-error"]').text()).toContain('接口尚未发布')
    expect(wrapper.find('[data-testid="experience-case-success"]').exists()).toBe(false)
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
    expect(wrapper.get('[data-testid="service-recovery-card"]').text()).toContain('刷新商品目录')
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
