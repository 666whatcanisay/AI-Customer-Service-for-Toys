import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { TesterIdentityKey } from '@/workspace/testerIdentity'
import HumanInLoopWorkspace from './HumanInLoopWorkspace.vue'

const apiMocks = vi.hoisted(() => ({
  listStores: vi.fn(),
  listProducts: vi.fn(),
  listSkus: vi.fn(),
  chat: vi.fn(),
  submitInteraction: vi.fn()
}))

vi.mock('@/api/platformClient', () => ({
  platformClient: {
    listStores: apiMocks.listStores,
    listProducts: apiMocks.listProducts,
    listSkus: apiMocks.listSkus
  }
}))

vi.mock('@/api/ragClient', () => ({ ragClient: { chat: apiMocks.chat } }))

vi.mock('@/api/aiInteractionEventClient', () => ({
  aiInteractionEventClient: { submit: apiMocks.submitInteraction },
  createAiInteractionEventIdempotencyKey: () => 'interaction-key-1'
}))

vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn() }
}))

const store = {
  tenantId: 'TENANT-1', platform: 'pinduoduo', storeCode: 'STORE-1', name: '演示积木店',
  dataSource: 'PILOT', customerServiceStatus: 'ENABLED', allowAutoSend: false
}
const product = {
  productId: 'PRODUCT-1', platform: 'pinduoduo', storeCode: 'STORE-1', officialName: '创意积木',
  displayName: '创意积木', salesStatus: 'ON_SALE', ageMin: 5, ageMax: 12, safetySummary: null,
  knowledgeStatus: 'APPROVED', dataSource: 'PILOT', customerServiceStatus: 'ENABLED'
}

const envelope = <T,>(items: T[]) => ({
  schemaVersion: 'pilot-business-catalog.v1.1', resultStatus: 'COMPLETE', items,
  total: items.length, warnings: []
})

describe('HumanInLoopWorkspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.listStores.mockResolvedValue(envelope([store]))
    apiMocks.listProducts.mockResolvedValue(envelope([product]))
    apiMocks.listSkus.mockResolvedValue(envelope([]))
    apiMocks.chat.mockResolvedValue({
      requestId: 'request-1', model: 'local-model', answer: '您好，这款积木建议 5 岁以上使用。',
      action: 'CONTROLLED_ANSWER', riskLevel: 'LOW', warnings: [], requiredFields: [],
      context: { tenant_id: 'TENANT-1', platform: 'pinduoduo', store_code: 'STORE-1', product_id: 'PRODUCT-1', sku_id: null },
      citations: [{
        file: '商品知识.md', page: null, chunkId: 'chunk-1', summary: '建议年龄 5 岁以上', distance: 0.1,
        knowledgeVersion: 'v1', sourceIds: ['source-1'], productId: 'PRODUCT-1', skuId: null
      }], latencyMs: 120
    })
    apiMocks.submitInteraction.mockResolvedValue({
      eventId: 'AIE-001', interactionId: 'request-1', status: 'RECORDED', occurredAt: '2026-08-06T08:02:00Z'
    })
  })

  const mountWorkspace = () => mount(HumanInLoopWorkspace, {
    global: {
      plugins: [createPinia()],
      provide: {
        [TesterIdentityKey as symbol]: {
          identity: ref({ reporterId: 'TESTER-ONE', reporterName: '客服小木', defaultStoreCode: 'STORE-1' }),
          save: vi.fn(), reload: vi.fn()
        }
      }
    }
  })

  it('runs a mock message through real adapters, evidence and edited acceptance', async () => {
    const wrapper = mountWorkspace()
    await flushPromises()

    expect(wrapper.get('[data-testid="conversation-center"]').text()).toContain('模拟渠道')
    expect(wrapper.get('[data-testid="workspace-context"]').text()).toContain('演示积木店')
    await wrapper.get('[data-testid="generate-draft"]').trigger('click')
    await flushPromises()

    expect(apiMocks.chat).toHaveBeenCalledWith(expect.objectContaining({
      context: expect.objectContaining({ product_id: 'PRODUCT-1', sku_id: null })
    }))
    expect((wrapper.get('[data-testid="reply-draft-editor"]').element as HTMLTextAreaElement).value)
      .toBe('您好，这款积木建议 5 岁以上使用。')
    expect(wrapper.get('[data-testid="knowledge-evidence"]').text()).toContain('商品知识')

    await wrapper.get('[data-testid="reply-draft-editor"]').setValue('您好，这款积木建议 5 岁以上使用，并请家长陪同。')
    await wrapper.get('[data-testid="edited-accept"]').trigger('click')
    await flushPromises()

    expect(apiMocks.submitInteraction).toHaveBeenCalledWith(expect.objectContaining({
      actionType: 'EDITED_ACCEPT',
      finalAnswerSummary: '您好，这款积木建议 5 岁以上使用，并请家长陪同。'
    }), 'interaction-key-1')
    expect(wrapper.get('[data-testid="interaction-receipt"]').text()).toContain('AIE-001')
    expect(wrapper.get('[data-testid="decision-center"]').text()).toContain('Approved')
    expect(wrapper.text()).toContain('系统不自动发送')
  })

  it('expires the visible draft when a new mock message arrives', async () => {
    const wrapper = mountWorkspace()
    await flushPromises()
    await wrapper.get('[data-testid="generate-draft"]').trigger('click')
    await flushPromises()

    await wrapper.get('#mock-message').setValue('还有其他注意事项吗？')
    await wrapper.get('[data-testid="mock-message-form"]').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[data-testid="draft-card"]').text()).toContain('Message Received')
    expect(wrapper.get('[data-testid="message-timeline"]').text()).toContain('还有其他注意事项吗？')
  })

  it('records a direct acceptance without changing the AI answer', async () => {
    const wrapper = mountWorkspace()
    await flushPromises()
    await wrapper.get('[data-testid="generate-draft"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="direct-accept"]').trigger('click')
    await flushPromises()

    expect(apiMocks.submitInteraction).toHaveBeenCalledWith(expect.objectContaining({
      actionType: 'DIRECT_ACCEPT',
      finalAnswerSummary: '您好，这款积木建议 5 岁以上使用。'
    }), 'interaction-key-1')
    expect(wrapper.get('[data-testid="decision-center"]').text()).toContain('Approved')
  })

  it('records rejection with no final answer and exposes the feedback-loop state', async () => {
    const wrapper = mountWorkspace()
    await flushPromises()
    await wrapper.get('[data-testid="generate-draft"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="reject-draft"]').trigger('click')
    await flushPromises()

    expect(apiMocks.submitInteraction).toHaveBeenCalledWith(expect.objectContaining({
      actionType: 'REJECTED', finalAnswerSummary: null
    }), 'interaction-key-1')
    expect(wrapper.get('[data-testid="decision-center"]').text()).toContain('Rejected')
    expect(wrapper.text()).toContain('反馈已沉淀')
  })
})
