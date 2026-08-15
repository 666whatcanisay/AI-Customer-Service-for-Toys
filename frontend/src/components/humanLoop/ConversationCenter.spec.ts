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
        conversationCounts: { NEW: 0, PROCESSING: 0, WAITING_REPLY: 1, COMPLETED: 0 }
      }
    })

    const item = wrapper.get('[data-testid="conversation-conversation-1"]')
    expect(item.text()).toContain('待确认')
    expect(item.text()).not.toContain('WAITING_CONFIRMATION')
    expect(item.text()).not.toContain('客服连接程序')
    expect(item.text()).not.toContain('待人工发送')
  })
})
