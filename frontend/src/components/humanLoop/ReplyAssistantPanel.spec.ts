import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { ReplyDraft, WorkspaceConversation } from '@/stores/humanLoopWorkspace'
import ReplyAssistantPanel from './ReplyAssistantPanel.vue'

const preparationId = `execution-preparation:${'a'.repeat(64)}`

const conversation: WorkspaceConversation = {
  conversationId: 'conversation-1', customerLabel: '客户 01',
  customerReference: `sha256:${'b'.repeat(64)}`, unreadCount: 0,
  source: 'CHANNEL_AGENT', status: 'WAITING_REPLY', messages: []
}

const draft: ReplyDraft = {
  draftId: 'draft-1', conversationId: 'conversation-1', messageId: 'message-1',
  state: 'HUMAN_REVIEW', decisionState: 'WAITING_HUMAN', replySource: 'AI',
  originalAnswer: '建议回复', editedAnswer: '建议回复', requestId: 'request-1',
  decisionId: 'decision-1', action: 'DIRECT_ANSWER', riskLevel: 'LOW', citations: [],
  warnings: [], requiredFields: [], hostState: 'EXECUTION_PREPARED', qualityStatus: 'PASS',
  policyMode: 'MANUAL_CONFIRM', preparationId, traceId: `trace:${'c'.repeat(64)}`,
  createdAt: '2026-08-12T00:00:00Z', updatedAt: '2026-08-12T00:01:00Z'
}

describe('ReplyAssistantPanel prepared-state recovery', () => {
  it('shows one useful empty state before a conversation is selected', () => {
    const wrapper = mount(ReplyAssistantPanel, {
      props: {
        conversation: null, draft: null, stores: [], products: [], skus: [], selectedStoreId: 8,
        selectedProductId: '', selectedSkuId: '', contextLoading: false, contextError: '',
        contextStatus: '店铺已自动加载', busy: false, actionBusy: false, actionError: '',
        agentStatus: 'ONLINE', canGenerateReply: true, canSubmitFeedback: true,
        feedbackBusy: false, feedbackReceiptId: ''
      }
    })

    expect(wrapper.get('[data-testid="assistant-empty-state"]').text()).toContain('从左侧选择一条待处理会话')
    expect(wrapper.find('[data-testid="workspace-context"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="draft-card"]').exists()).toBe(false)
  })

  it('keeps desktop product context compact and removes the duplicated store selector', async () => {
    const wrapper = mount(ReplyAssistantPanel, {
      props: {
        conversation, draft, stores: [{
          storeId: 8, tenantId: 'tenant-1', storeCode: 'STORE-1', storeName: '演示店铺',
          platform: 'pdd', isDefault: true
        }],
        products: [{ productId: 'product-1', displayName: '创意积木' }], skus: [],
        selectedStoreId: 8, selectedProductId: 'product-1', selectedSkuId: '',
        contextLoading: false, contextError: '', contextStatus: '上下文已自动识别',
        busy: false, actionBusy: false, actionError: '', agentStatus: 'ONLINE',
        canGenerateReply: true, canSubmitFeedback: true, feedbackBusy: false,
        feedbackReceiptId: '', showStoreSelector: false
      }
    })

    const toggle = wrapper.get('[data-testid="context-toggle"]')
    expect(toggle.attributes('aria-expanded')).toBe('false')
    expect(toggle.text()).toContain('创意积木')
    await toggle.trigger('click')
    expect(toggle.attributes('aria-expanded')).toBe('true')
    expect(wrapper.findAll('[data-testid="workspace-context"] select')).toHaveLength(2)
    expect(wrapper.get('[data-testid="workspace-context"]').text()).not.toContain('演示店铺')
  })

  it('hides review and regeneration controls whenever preparation already exists', () => {
    const wrapper = mount(ReplyAssistantPanel, {
      props: {
        conversation, draft, stores: [], products: [], skus: [], selectedStoreId: 8,
        selectedProductId: '', selectedSkuId: '', contextLoading: false, contextError: '',
        contextStatus: '已就绪', busy: false, actionBusy: false, actionError: '',
        agentStatus: 'ONLINE', canGenerateReply: true, canSubmitFeedback: true,
        feedbackBusy: false, feedbackReceiptId: ''
      }
    })

    expect(wrapper.get('[data-testid="draft-card"]').text()).toContain('执行已准备')
    expect(wrapper.find('[data-testid="direct-accept"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="regenerate-draft"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="edit-draft"]').exists()).toBe(false)
  })

  it('deduplicates readable knowledge evidence and renders scope once', async () => {
    const citation = {
      file: '商品知识', page: null, chunkId: 'technical-id', summary: '适合5岁以上使用。',
      distance: null, knowledgeVersion: null, sourceIds: [], productId: 'product-1', skuId: null
    }
    const wrapper = mount(ReplyAssistantPanel, {
      props: {
        conversation, draft: { ...draft, citations: [citation, citation] }, stores: [], products: [], skus: [], selectedStoreId: 8,
        selectedProductId: '', selectedSkuId: '', contextLoading: false, contextError: '',
        contextStatus: '已就绪', busy: false, actionBusy: false, actionError: '',
        agentStatus: 'ONLINE', canGenerateReply: true, canSubmitFeedback: true,
        feedbackBusy: false, feedbackReceiptId: ''
      },
      global: { stubs: { Teleport: true } }
    })
    await wrapper.get('[data-testid="open-knowledge-evidence"]').trigger('click')
    const dialog = wrapper.get('[data-testid="knowledge-evidence-dialog"]')
    expect(dialog.findAll('article')).toHaveLength(1)
    expect(dialog.text()).toContain('适合5岁以上使用。')
    expect(dialog.text().match(/已匹配当前商品/g)).toHaveLength(1)
  })
})
