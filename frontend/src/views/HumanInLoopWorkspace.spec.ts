import { flushPromises, mount } from '@vue/test-utils'
import { createPinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { authSessionTestControl, type AuthUser } from '@/auth/authSession'
import { DesktopAgentClientError } from '@/api/desktopAgentTypes'
import HumanInLoopWorkspace from './HumanInLoopWorkspace.vue'

const apiMocks = vi.hoisted(() => ({
  getContext: vi.fn(),
  resolve: vi.fn(),
  chat: vi.fn(),
  submitInteraction: vi.fn(),
  submitFeedback: vi.fn(),
  createInteractionKey: vi.fn(),
  createFeedbackKey: vi.fn(),
  getDesktopStatus: vi.fn(),
  requestBindingGrant: vi.fn()
}))

vi.mock('@/api/storeContextClient', () => ({
  storeContextClient: {
    getContext: apiMocks.getContext,
    resolve: apiMocks.resolve
  }
}))

vi.mock('@/api/desktopAgentClient', () => ({
  desktopAgentClient: {
    getStatus: apiMocks.getDesktopStatus,
    requestBindingGrant: apiMocks.requestBindingGrant
  }
}))

vi.mock('@/api/ragClient', () => ({ ragClient: { chat: apiMocks.chat } }))

vi.mock('@/api/aiInteractionEventClient', () => ({
  aiInteractionEventClient: { submit: apiMocks.submitInteraction },
  createAiInteractionEventIdempotencyKey: apiMocks.createInteractionKey
}))

vi.mock('@/api/aiResponseFeedbackClient', () => ({
  aiResponseFeedbackClient: { submit: apiMocks.submitFeedback },
  createAiResponseFeedbackIdempotencyKey: apiMocks.createFeedbackKey
}))

vi.mock('element-plus', () => ({
  ElMessage: { info: vi.fn(), success: vi.fn() }
}))

const store = { storeId: 8, tenantId: 'TENANT-1', platform: 'pinduoduo', storeCode: 'STORE-1', storeName: '演示积木店', isDefault: true }
const product = { productId: 'PRODUCT-1', displayName: '创意积木' }
const authenticatedUser = (): AuthUser => ({
  id: '11111111-1111-4111-8111-111111111111', username: 'support.one',
  display_name: '客服小木', status: 'ACTIVE', roles: ['CUSTOMER_SERVICE'],
  permissions: ['workspace.access', 'ai.reply', 'feedback.submit'],
  stores: [{ id: 1, store_id: 8, store_code: 'STORE-1', store_name: '演示积木店', platform: 'pinduoduo', is_default: true }],
  must_change_password: false, all_store_access: false,
  created_at: '2026-08-06T00:00:00Z', updated_at: '2026-08-06T00:00:00Z'
})
const chatResult = {
  requestId: 'request-1', model: 'local-model', answer: '您好，这款积木建议 5 岁以上使用。',
  action: 'CONTROLLED_ANSWER', riskLevel: 'LOW', warnings: [], requiredFields: [],
  context: { tenant_id: 'TENANT-1', platform: 'pinduoduo', store_code: 'STORE-1', product_id: 'PRODUCT-1', sku_id: null },
  citations: [{
    file: '商品知识.md', page: null, chunkId: 'chunk-1', summary: '建议年龄 5 岁以上', distance: 0.1,
    knowledgeVersion: 'v1', sourceIds: ['source-1'], productId: 'PRODUCT-1', skuId: null
  }], latencyMs: 120
}

describe('HumanInLoopWorkspace', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.createInteractionKey.mockReturnValue('interaction-key-1')
    apiMocks.createFeedbackKey.mockReturnValue('feedback-key-1')
    authSessionTestControl.setUser(authenticatedUser())
    apiMocks.getContext.mockResolvedValue({
      userId: '11111111-1111-4111-8111-111111111111', roles: ['CUSTOMER_SERVICE'],
      allStoreAccess: false, state: 'READY', stores: [store], effectiveStore: store
    })
    apiMocks.resolve.mockResolvedValue({
      resolutionId: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa', status: 'RESOLVED',
      store, product, sku: null, productCandidates: [product], skuCandidates: [],
      reasonCode: 'PRODUCT_RESOLVED_NO_SKU', createdAt: '2026-08-06T08:00:00Z'
    })
    apiMocks.chat.mockResolvedValue(chatResult)
    apiMocks.submitInteraction.mockResolvedValue({
      eventId: 'AIE-001', interactionId: 'request-1', status: 'RECORDED', occurredAt: '2026-08-06T08:02:00Z'
    })
    apiMocks.submitFeedback.mockResolvedValue({ feedbackId: 'ARF-001', status: 'NEW' })
    apiMocks.getDesktopStatus.mockResolvedValue({
      userId: '11111111-1111-4111-8111-111111111111', storeId: 8,
      storeCode: 'STORE-1', associationState: 'READY',
      agent: {
        agentId: 'agent-1', deviceId: 'device-1', deviceName: 'CS-PC-01',
        agentVersion: '1.1.0', identityStatus: 'ACTIVE', onlineStatus: 'ONLINE',
        runtimeStatus: 'ONLINE', productionEligible: true, bindingRevision: 2,
        lastHeartbeat: '2026-08-06T08:00:00Z'
      }, checkedAt: '2026-08-06T08:00:01Z'
    })
    apiMocks.requestBindingGrant.mockResolvedValue({
      grantId: 'grant-1', agentId: 'agent-1', deviceId: 'device-1',
      bindingCode: 'ABCDEF0123456789ABCDEF0123456789',
      expiresAt: new Date(Date.now() + 10 * 60 * 1000).toISOString()
    })
  })

  const mountWorkspace = () => mount(HumanInLoopWorkspace, {
    global: { plugins: [createPinia()] }
  })

  it('runs a controlled conversation through context, evidence and edited acceptance', async () => {
    const wrapper = mountWorkspace()
    await flushPromises()

    expect(wrapper.get('[data-testid="conversation-center"]').text()).toContain('受控人工会话')
    expect(wrapper.get('[data-testid="desktop-agent-panel"]').text()).toContain('CS-PC-01')
    expect(wrapper.get('[data-testid="desktop-agent-panel"]').text()).toContain('1.1.0')
    expect(wrapper.get('[data-testid="desktop-agent-online-status"]').text()).toContain('设备在线')
    expect(wrapper.get('[data-testid="agent-status"]').text()).toContain('处理中')
    expect(wrapper.get('[data-testid="workspace-context"]').text()).toContain('演示积木店')
    await wrapper.get('[data-testid="generate-draft"]').trigger('click')
    await flushPromises()

    expect(apiMocks.resolve).toHaveBeenCalledWith(expect.objectContaining({ storeId: 8 }))
    expect(apiMocks.chat).toHaveBeenCalledWith({
      question: expect.any(String), resolution_id: 'aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa'
    })
    expect((wrapper.get('[data-testid="reply-draft-editor"]').element as HTMLTextAreaElement).value)
      .toBe('您好，这款积木建议 5 岁以上使用。')
    expect(wrapper.get('[data-testid="knowledge-evidence"]').text()).toContain('商品知识')
    await wrapper.get('[data-testid="open-knowledge-evidence"]').trigger('click')
    await flushPromises()
    const evidenceDialog = document.body.querySelector('[data-testid="knowledge-evidence-dialog"]')
    expect(evidenceDialog?.textContent).toContain('商品与知识依据')
    expect(evidenceDialog?.textContent).toContain('建议年龄 5 岁以上')
    ;(document.body.querySelector('[data-testid="close-knowledge-evidence"]') as HTMLButtonElement).click()
    await flushPromises()
    expect(document.body.querySelector('[data-testid="knowledge-evidence-dialog"]')).toBeNull()

    await wrapper.get('[data-testid="edit-draft"]').trigger('click')
    await wrapper.get('[data-testid="reply-draft-editor"]').setValue('您好，这款积木建议 5 岁以上使用，并请家长陪同。')
    await wrapper.get('[data-testid="edited-accept"]').trigger('click')
    await flushPromises()

    expect(apiMocks.submitInteraction).toHaveBeenCalledWith(expect.objectContaining({
      actionType: 'EDITED_ACCEPT',
      finalAnswerSummary: '您好，这款积木建议 5 岁以上使用，并请家长陪同。',
      createdBy: '11111111-1111-4111-8111-111111111111'
    }), 'interaction-key-1')
    expect(wrapper.get('[data-testid="interaction-receipt"]').text()).toContain('采用结果已记录')
    expect(wrapper.get('[data-testid="interaction-receipt"]').text()).not.toContain('AIE-001')
    expect(wrapper.get('[data-testid="decision-center"]').text()).toContain('已采用')
    expect(wrapper.text()).toContain('系统不会自动发送')
  })

  it('expires the visible draft when a new manual message arrives', async () => {
    const wrapper = mountWorkspace()
    await flushPromises()
    await wrapper.get('[data-testid="generate-draft"]').trigger('click')
    await flushPromises()

    await wrapper.get('#manual-message').setValue('还有其他注意事项吗？')
    await wrapper.get('[data-testid="manual-message-form"]').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[data-testid="draft-card"]').text()).toContain('已收到客户消息')
    expect(wrapper.get('[data-testid="message-timeline"]').text()).toContain('还有其他注意事项吗？')
  })

  it('creates a new controlled manual conversation without a channel connection', async () => {
    const wrapper = mountWorkspace(); await flushPromises()
    const modeButtons = wrapper.findAll('[data-testid="manual-message-form"] .intake-mode button')
    await modeButtons[1].trigger('click')
    await wrapper.get('#manual-customer-label').setValue('客户 C03')
    await wrapper.get('#manual-message').setValue('这款商品有哪些颜色？')
    await wrapper.get('[data-testid="manual-message-form"]').trigger('submit')
    await flushPromises()

    expect(wrapper.get('[data-testid="message-timeline"]').text()).toContain('客户 C03')
    expect(wrapper.get('[data-testid="message-timeline"]').text()).toContain('这款商品有哪些颜色？')
    expect(wrapper.get('[data-testid="message-timeline"]').text()).toContain('当前页面内存')
  })

  it('requires human Product confirmation before calling AI', async () => {
    const secondProduct = { productId: 'PRODUCT-2', displayName: '恐龙积木' }
    apiMocks.resolve
      .mockResolvedValueOnce({
        resolutionId: 'bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb',
        status: 'PRODUCT_CONFIRMATION_REQUIRED', store, product: null, sku: null,
        productCandidates: [product, secondProduct], skuCandidates: [],
        reasonCode: 'MULTIPLE_PRODUCT_MATCHES', createdAt: '2026-08-06T08:00:00Z'
      })
      .mockResolvedValueOnce({
        resolutionId: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc', status: 'RESOLVED',
        store, product, sku: null, productCandidates: [product], skuCandidates: [],
        reasonCode: 'PRODUCT_RESOLVED_NO_SKU', createdAt: '2026-08-06T08:01:00Z'
      })
    const wrapper = mountWorkspace(); await flushPromises()
    await wrapper.get('[data-testid="generate-draft"]').trigger('click'); await flushPromises()
    expect(apiMocks.chat).not.toHaveBeenCalled()
    expect(wrapper.text()).toContain('识别到多个商品')
    const productSelect = wrapper.findAll('[data-testid="workspace-context"] select')[1]
    await productSelect.setValue('PRODUCT-1')
    await wrapper.get('[data-testid="generate-draft"]').trigger('click'); await flushPromises()
    expect(apiMocks.chat).toHaveBeenCalledWith(expect.objectContaining({
      resolution_id: 'cccccccc-cccc-4ccc-8ccc-cccccccccccc'
    }))
  })

  it('keeps manual reply available when the product cannot be identified', async () => {
    apiMocks.resolve.mockResolvedValueOnce({
      resolutionId: 'dddddddd-dddd-4ddd-8ddd-dddddddddddd', status: 'UNKNOWN',
      store, product: null, sku: null, productCandidates: [], skuCandidates: [],
      reasonCode: 'PRODUCT_UNKNOWN', createdAt: '2026-08-06T08:00:00Z'
    })
    const wrapper = mountWorkspace(); await flushPromises()

    await wrapper.get('[data-testid="generate-draft"]').trigger('click'); await flushPromises()
    expect(apiMocks.chat).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="workspace-action-error"]').text()).toContain('直接在回复草稿中输入人工回复')

    const editor = wrapper.get('[data-testid="reply-draft-editor"]')
    await editor.setValue('您好，请提供商品照片，我们马上为您人工核对。')
    expect(wrapper.get('[data-testid="draft-card"]').text()).toContain('人工输入')
    expect(wrapper.get('[data-testid="knowledge-evidence"]').text()).toContain('未调用 AI')

    await wrapper.get('[data-testid="manual-accept"]').trigger('click'); await flushPromises()
    expect(apiMocks.submitInteraction).not.toHaveBeenCalled()
    expect(apiMocks.submitFeedback).not.toHaveBeenCalled()
    expect(wrapper.get('[data-testid="decision-center"]').text()).toContain('人工回复已确认')
    expect(wrapper.get('[data-testid="active-conversation-status"]').text()).toContain('待人工发送')
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
    expect(wrapper.get('[data-testid="decision-center"]').text()).toContain('已采用')
  })

  it('records rejection reason with the linked interaction before rejecting the draft', async () => {
    const wrapper = mountWorkspace()
    await flushPromises()
    await wrapper.get('[data-testid="generate-draft"]').trigger('click')
    await flushPromises()
    await wrapper.get('[data-testid="reject-draft"]').trigger('click')
    await wrapper.get('[data-testid="feedback-type"]').setValue('RISK_ISSUE')
    await wrapper.get('[data-testid="feedback-note"]').setValue('安全限制未突出')
    await wrapper.get('[data-testid="feedback-form"]').trigger('submit')
    await flushPromises()

    expect(apiMocks.submitInteraction).toHaveBeenCalledWith(expect.objectContaining({
      actionType: 'REJECTED', finalAnswerSummary: null
    }), 'interaction-key-1')
    expect(apiMocks.submitFeedback).toHaveBeenCalledWith(expect.objectContaining({
      feedbackType: 'RISK_ISSUE', feedbackNote: '安全限制未突出',
      interactionId: 'request-1', createdBy: '11111111-1111-4111-8111-111111111111'
    }), 'feedback-key-1')
    expect(wrapper.get('[data-testid="decision-center"]').text()).toContain('已拒绝')
    expect(wrapper.text()).toContain('反馈已沉淀')
  })

  it('does not reject locally when reason persistence fails and reuses both idempotency keys', async () => {
    apiMocks.submitFeedback
      .mockRejectedValueOnce(new Error('反馈服务暂时不可用'))
      .mockResolvedValueOnce({ feedbackId: 'ARF-RETRY', status: 'NEW' })
    const wrapper = mountWorkspace(); await flushPromises()
    await wrapper.get('[data-testid="generate-draft"]').trigger('click'); await flushPromises()
    await wrapper.get('[data-testid="reject-draft"]').trigger('click')
    await wrapper.get('[data-testid="feedback-form"]').trigger('submit'); await flushPromises()

    expect(wrapper.get('[data-testid="decision-center"]').text()).toContain('等待人工确认')
    expect(wrapper.get('[data-testid="workspace-action-error"]').text()).toContain('反馈服务暂时不可用')

    await wrapper.get('[data-testid="feedback-form"]').trigger('submit'); await flushPromises()
    expect(wrapper.get('[data-testid="decision-center"]').text()).toContain('已拒绝')
    expect(apiMocks.submitInteraction).toHaveBeenNthCalledWith(1, expect.any(Object), 'interaction-key-1')
    expect(apiMocks.submitInteraction).toHaveBeenNthCalledWith(2, expect.any(Object), 'interaction-key-1')
    expect(apiMocks.submitFeedback).toHaveBeenNthCalledWith(1, expect.any(Object), 'feedback-key-1')
    expect(apiMocks.submitFeedback).toHaveBeenNthCalledWith(2, expect.any(Object), 'feedback-key-1')
    expect(apiMocks.createInteractionKey).toHaveBeenCalledTimes(1)
    expect(apiMocks.createFeedbackKey).toHaveBeenCalledTimes(1)
  })

  it('marks an AI issue without making the human adoption decision', async () => {
    const wrapper = mountWorkspace(); await flushPromises()
    await wrapper.get('[data-testid="generate-draft"]').trigger('click'); await flushPromises()
    await wrapper.get('[data-testid="flag-issue"]').trigger('click')
    await wrapper.get('[data-testid="feedback-type"]').setValue('MISSING_INFO')
    await wrapper.get('[data-testid="feedback-form"]').trigger('submit')
    await flushPromises()

    expect(apiMocks.submitFeedback).toHaveBeenCalledWith(expect.objectContaining({
      feedbackType: 'MISSING_INFO'
    }), 'feedback-key-1')
    expect(wrapper.get('[data-testid="feedback-receipt"]').text()).toBe('问题反馈已记录。')
    expect(wrapper.get('[data-testid="decision-center"]').text()).toContain('等待人工确认')
  })

  it('moves an accepted conversation to waiting and requires explicit completion', async () => {
    const wrapper = mountWorkspace(); await flushPromises()
    await wrapper.get('[data-testid="generate-draft"]').trigger('click'); await flushPromises()
    await wrapper.get('[data-testid="direct-accept"]').trigger('click'); await flushPromises()
    expect(wrapper.get('[data-testid="active-conversation-status"]').text()).toContain('待人工发送')
    await wrapper.get('[data-testid="complete-conversation"]').trigger('click')
    expect(wrapper.get('[data-testid="active-conversation-status"]').text()).toContain('已完成')
  })

  it('blocks generation while the authenticated agent is offline', async () => {
    const wrapper = mountWorkspace(); await flushPromises()
    await wrapper.get('[data-testid="agent-offline"]').trigger('click')
    expect(wrapper.get('[data-testid="agent-status"]').text()).toContain('离线')
    expect((wrapper.get('[data-testid="generate-draft"]').element as HTMLButtonElement).disabled).toBe(true)
  })

  it('shows a real Agent offline warning without claiming the page is disconnected', async () => {
    apiMocks.getDesktopStatus.mockResolvedValueOnce({
      userId: '11111111-1111-4111-8111-111111111111', storeId: 8,
      storeCode: 'STORE-1', associationState: 'READY',
      agent: {
        agentId: 'agent-1', deviceId: 'device-1', deviceName: 'CS-PC-01',
        agentVersion: '1.1.0', identityStatus: 'ACTIVE', onlineStatus: 'OFFLINE',
        runtimeStatus: 'STOPPED', productionEligible: true, bindingRevision: 3,
        lastHeartbeat: '2026-08-06T07:30:00Z'
      }, checkedAt: '2026-08-06T08:00:01Z'
    })
    const wrapper = mountWorkspace(); await flushPromises()
    expect(wrapper.get('[data-testid="desktop-agent-online-status"]').text()).toContain('设备离线')
    expect(wrapper.get('[data-testid="desktop-agent-notice"]').text()).toContain('当前无法使用渠道连接能力')
    expect((wrapper.get('[data-testid="generate-draft"]').element as HTMLButtonElement).disabled).toBe(false)
  })

  it('distinguishes upstream permission expiry from an offline Agent', async () => {
    apiMocks.getDesktopStatus.mockRejectedValueOnce(new DesktopAgentClientError(
      'permission_invalid', 'Agent 接入权限已失效，请联系管理员更新授权。', 503
    ))
    const wrapper = mountWorkspace(); await flushPromises()
    expect(wrapper.get('[data-testid="desktop-agent-online-status"]').text()).toContain('权限失效')
    expect(wrapper.get('[data-testid="desktop-agent-notice"]').text()).toContain('接入权限已失效')
  })

  it('requests a one-time device-bound grant and keeps activation explicit', async () => {
    apiMocks.getDesktopStatus.mockResolvedValueOnce({
      userId: '11111111-1111-4111-8111-111111111111', storeId: 8,
      storeCode: 'STORE-1', associationState: 'BINDING_REQUIRED',
      agent: null, checkedAt: '2026-08-06T08:00:01Z'
    })
    const wrapper = mountWorkspace(); await flushPromises()
    const inputs = wrapper.findAll('[data-testid="desktop-binding-form"] input')
    await inputs[0].setValue('agent-1')
    await inputs[1].setValue('device-1')
    await wrapper.get('[data-testid="desktop-binding-form"]').trigger('submit')
    await flushPromises()
    expect(apiMocks.requestBindingGrant).toHaveBeenCalledWith({
      agentId: 'agent-1', deviceId: 'device-1', storeId: 8
    })
    expect(wrapper.get('[data-testid="desktop-binding-grant"]').text()).toContain('ABCDEF0123456789')
    expect(wrapper.get('[data-testid="desktop-binding-grant"]').text()).toContain('如看不到设备绑定页面，请联系管理员')
  })

  it('blocks review when the selected product knowledge is not published', async () => {
    apiMocks.chat.mockResolvedValueOnce({
      ...chatResult,
      answer: '该商品已进入客服目录，但AI知识尚未同步，请人工核对商品资料。',
      action: 'REFUSE', riskLevel: 'HIGH', citations: [],
      warnings: ['KNOWLEDGE_NOT_PUBLISHED']
    })
    const wrapper = mountWorkspace(); await flushPromises()
    await wrapper.get('[data-testid="generate-draft"]').trigger('click'); await flushPromises()

    expect(wrapper.get('[data-testid="workspace-action-error"]').text())
      .toContain('该商品的 AI 知识尚未发布，请联系运营完成知识发布后重试')
    expect(wrapper.find('[data-testid="direct-accept"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('KNOWLEDGE_NOT_PUBLISHED')
  })

  it('keeps feedback controls disabled when the authenticated user lacks feedback permission', async () => {
    authSessionTestControl.setUser({
      ...authenticatedUser(), permissions: ['workspace.access', 'ai.reply']
    })
    const wrapper = mountWorkspace(); await flushPromises()
    await wrapper.get('[data-testid="generate-draft"]').trigger('click'); await flushPromises()
    expect((wrapper.get('[data-testid="direct-accept"]').element as HTMLButtonElement).disabled).toBe(true)
    expect((wrapper.get('[data-testid="flag-issue"]').element as HTMLButtonElement).disabled).toBe(true)
  })
})
