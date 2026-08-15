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
  it('keeps an empty workspace to one compact rail without placeholder metrics', async () => {
    const wrapper = mount(DecisionCenter, {
      props: {
        draft: null, conversation: null, receiptId: '', feedbackReceiptId: '', collapsed: true
      }
    })

    expect(wrapper.get('[data-testid="decision-center"]').text()).toContain('未选择会话')
    expect(wrapper.text()).not.toContain('置信度')
    expect(wrapper.text()).not.toContain('知识覆盖')
    await wrapper.get('[data-testid="decision-panel-expand"]').trigger('click')
    expect(wrapper.emitted('toggle')).toHaveLength(1)
  })

  it('highlights a waiting high-risk decision while remaining collapsed', () => {
    const wrapper = mount(DecisionCenter, {
      props: {
        draft: { ...draft, state: 'HUMAN_REVIEW', decisionState: 'WAITING_HUMAN', riskLevel: 'HIGH' },
        conversation: { ...conversation, requiresHuman: true, attentionLevel: 'HUMAN_REQUIRED' },
        receiptId: '', feedbackReceiptId: '', collapsed: true
      }
    })

    expect(wrapper.get('[data-testid="decision-center"]').classes()).toContain('needs-attention')
    expect(wrapper.text()).toContain('需人工 1')
    expect(wrapper.text()).toContain('风险 高')
    expect(wrapper.text()).toContain('REAL_SEND')
  })

  it('shows the shared production real-send state instead of guessing from the conversation', () => {
    const wrapper = mount(DecisionCenter, {
      global: {
        provide: { channelAgentRealSendEnabled: { value: true } }
      },
      props: {
        draft: { ...draft, state: 'HUMAN_REVIEW', decisionState: 'WAITING_HUMAN' },
        conversation: { ...conversation, autoReplyRunning: false, requiresHuman: true },
        receiptId: '', feedbackReceiptId: '', collapsed: false
      }
    })

    expect(wrapper.text()).toContain('REAL_SEND = ON')
    expect(wrapper.text()).toContain('逐消息授权')
  })

  it('reveals the reply and emits the existing human confirmation action when expanded', async () => {
    const reviewDraft = {
      ...draft, state: 'HUMAN_REVIEW' as const, decisionState: 'WAITING_HUMAN' as const,
      hostState: 'WAITING_APPROVAL', preparationId: null
    }
    const wrapper = mount(DecisionCenter, {
      props: {
        draft: reviewDraft, conversation, receiptId: '', feedbackReceiptId: '', collapsed: false
      }
    })

    expect(wrapper.text()).toContain('建议回复')
    expect(wrapper.text()).toContain('REAL_SEND = OFF')
    await wrapper.get('[data-testid="decision-confirm"]').trigger('click')
    expect(wrapper.emitted('confirm')?.[0]).toEqual(['DIRECT_ACCEPT'])
  })

  it('never presents an execution preparation as a real send receipt', () => {
    const wrapper = mount(DecisionCenter, {
      props: { draft, conversation, receiptId: '', feedbackReceiptId: '' }
    })

    expect(wrapper.get('[data-testid="execution-preparation"]').text())
      .toContain('尚未发送真实 PDD 消息')
    expect(wrapper.get('[data-testid="prepared-send-boundary"]').text())
      .toContain('未产生真实 Receipt 前不能标记为已发送')
    expect(wrapper.find('[data-testid="execution-receipt"]').exists()).toBe(false)
    expect(wrapper.find('[data-testid="complete-conversation"]').exists()).toBe(false)
    expect(wrapper.text()).not.toContain('已确认发送到当前 PDD 会话')
    expect(wrapper.text()).not.toContain('已发送并生成不可变回执')
  })
})

describe('DecisionCenter automatic mode', () => {
  it('reduces a running automatic conversation to status-only content', () => {
    const wrapper = mount(DecisionCenter, {
      props: {
        draft,
        conversation: {
          ...conversation,
          autoReplyRunning: true,
          requiresHuman: false,
          attentionLevel: 'UNANSWERED'
        },
        receiptId: '', feedbackReceiptId: '', collapsed: false
      }
    })

    expect(wrapper.find('[data-testid="automatic-reply-status"]').exists()).toBe(true)
    expect(wrapper.find('[data-testid="decision-confirm"]').exists()).toBe(false)
  })
})
