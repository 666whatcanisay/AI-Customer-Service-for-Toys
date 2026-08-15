import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'

import type { WorkspaceConversation } from '@/stores/humanLoopWorkspace'
import ConversationCenter from './ConversationCenter.vue'

describe('ConversationCenter', () => {
  it('shows a compact human label instead of raw Agent processing codes', () => {
    const conversation: WorkspaceConversation = {
      conversationId: 'conversation-1',
      customerLabel: '客户 6fa965da1af2',
      unreadCount: 0,
      source: 'CHANNEL_AGENT',
      status: 'WAITING_REPLY',
      processingStage: 'WAITING_CONFIRMATION',
      messages: [{
        messageId: 'message-1',
        conversationId: 'conversation-1',
        customerLabel: '客户 6fa965da1af2',
        content: '跑起来跟蚂蚁一样',
        receivedAt: '2026-08-15T05:13:00Z',
        source: 'CHANNEL_AGENT',
        senderRole: 'CUSTOMER',
        direction: 'INBOUND'
      }]
    }
    const wrapper = mount(ConversationCenter, {
      props: {
        conversations: [conversation],
        activeConversationId: conversation.conversationId,
        agentStatus: 'BUSY',
        conversationCounts: { NEW: 0, PROCESSING: 0, WAITING_REPLY: 1, COMPLETED: 0 },
        confirmingConversationId: ''
      }
    })

    const item = wrapper.get('[data-testid="conversation-conversation-1"]')
    expect(item.text()).toContain('待确认')
    expect(item.text()).not.toContain('WAITING_CONFIRMATION')
    expect(item.text()).not.toContain('客服连接程序')
    expect(item.text()).not.toContain('待人工发送')
  })
})

describe('ConversationCenter attention ordering', () => {
  it('pins human-required red cards, then unanswered yellow cards, with newest first', () => {
    const makeConversation = (
      conversationId: string,
      attentionLevel: 'HUMAN_REQUIRED' | 'UNANSWERED' | 'NONE',
      receivedAt: string
    ): WorkspaceConversation => ({
      conversationId,
      customerLabel: conversationId,
      unreadCount: 1,
      source: 'CHANNEL_AGENT',
      status: 'NEW',
      attentionLevel,
      requiresHuman: attentionLevel === 'HUMAN_REQUIRED',
      messages: [{
        messageId: `message-${conversationId}`,
        conversationId,
        customerLabel: conversationId,
        content: conversationId,
        receivedAt,
        source: 'CHANNEL_AGENT',
        senderRole: 'CUSTOMER',
        direction: 'INBOUND'
      }]
    })
    const wrapper = mount(ConversationCenter, {
      props: {
        conversations: [
          makeConversation('normal', 'NONE', '2026-08-15T08:30:00Z'),
          makeConversation('yellow-old', 'UNANSWERED', '2026-08-15T08:10:00Z'),
          makeConversation('red-old', 'HUMAN_REQUIRED', '2026-08-15T08:00:00Z'),
          makeConversation('yellow-new', 'UNANSWERED', '2026-08-15T08:20:00Z'),
          makeConversation('red-new', 'HUMAN_REQUIRED', '2026-08-15T08:25:00Z')
        ],
        activeConversationId: '',
        agentStatus: 'ONLINE',
        conversationCounts: { NEW: 5, PROCESSING: 0, WAITING_REPLY: 0, COMPLETED: 0 },
        confirmingConversationId: ''
      }
    })

    expect(wrapper.findAll('.conversation-item').map((item) => item.attributes('data-testid')))
      .toEqual([
        'conversation-red-new',
        'conversation-red-old',
        'conversation-yellow-new',
        'conversation-yellow-old',
        'conversation-normal'
      ])
    expect(wrapper.get('[data-testid="conversation-red-new"]').classes()).toContain('requires-human')
    expect(wrapper.get('[data-testid="conversation-yellow-new"]').classes()).toContain('awaiting-reply')
  })

  it('offers an explicit local confirmation for the selected attention card', async () => {
    const conversation: WorkspaceConversation = {
      conversationId: 'conversation-attention',
      customerLabel: '客户 A',
      unreadCount: 1,
      source: 'CHANNEL_AGENT',
      status: 'NEW',
      attentionLevel: 'UNANSWERED',
      messages: [{
        messageId: 'message-1',
        conversationId: 'conversation-attention',
        customerLabel: '客户 A',
        content: '已在 PDD 回复',
        receivedAt: '2026-08-15T09:00:00Z',
        source: 'CHANNEL_AGENT',
        senderRole: 'CUSTOMER',
        direction: 'INBOUND'
      }]
    }
    const wrapper = mount(ConversationCenter, {
      props: {
        conversations: [conversation],
        activeConversationId: conversation.conversationId,
        agentStatus: 'ONLINE',
        conversationCounts: { NEW: 1, PROCESSING: 0, WAITING_REPLY: 0, COMPLETED: 0 },
        confirmingConversationId: ''
      }
    })

    await wrapper.get('[data-testid="confirm-current-replied"]').trigger('click')
    expect(wrapper.emitted('confirmReplied')).toEqual([[conversation.conversationId]])
  })
})
