import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { ReplyDraft, WorkspaceConversation } from '@/stores/humanLoopWorkspace'
import DecisionCenter from './DecisionCenter.vue'

const preparationId = `execution-preparation:${'a'.repeat(64)}`

const conversation: WorkspaceConversation = {
  conversationId: 'conversation-1',
  customerLabel: '客户 01',
  customerReference: `sha256:${'b'.repeat(64)}`,
  status: 'WAITING_REPLY',
  unreadCount: 0,
  source: 'CHANNEL_AGENT',
  messages: []
}

const draft: ReplyDraft = {
  draftId: 'draft-1', conversationId: 'conversation-1', messageId: 'message-1',
  state: 'ACCEPTED', decisionState: 'APPROVED', replySource: 'AI',
  originalAnswer: '建议回复', editedAnswer: '建议回复', requestId: 'request-1',
  decisionId: 'decision-1', action: 'DIRECT_ANSWER', riskLevel: 'LOW', citations: [],
  warnings: ['SUGGESTION_ONLY'], requiredFields: [], hostState: 'EXECUTION_PREPARED',
  qualityStatus: 'PASS', policyMode: 'MANUAL_CONFIRM', preparationId,
  traceId: `trace:${'c'.repeat(64)}`, createdAt: '2026-08-12T00:00:00Z',
  updatedAt: '2026-08-12T00:01:00Z'
}

describe('DecisionCenter execution preparation boundary', () => {
  it('never presents an execution preparation as a real send receipt', () => {
    const wrapper = mount(DecisionCenter, {
      props: { draft, conversation, receiptId: '', feedbackReceiptId: '' }
    })

    expect(wrapper.get('[data-testid="execution-preparation"]').text())
      .toContain('尚未发送真实 PDD 消息')
    expect(wrapper.get('[data-testid="prepared-send-boundary"]').text())
      .toContain('不能标记为已发送')
    expect(wrapper.find('[data-testid="execution-receipt"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="complete-conversation"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('已确认发送到当前 PDD 会话')
    expect(wrapper.text()).not.toContain('已发送并生成不可变回执')
  })
})
