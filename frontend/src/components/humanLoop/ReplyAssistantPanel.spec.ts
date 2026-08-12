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
})
