import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it } from 'vitest'

import { useHumanLoopWorkspaceStore } from './humanLoopWorkspace'
import type { ChannelConversationSeed } from '@/workspace/channelMessageAdapter'

const seed: ChannelConversationSeed = {
  conversationId: 'conversation-1',
  customerLabel: '客户 A01',
  unreadCount: 1,
  source: 'MANUAL',
  messages: [{
    messageId: 'message-1',
    conversationId: 'conversation-1',
    customerLabel: '客户 A01',
    content: '适合多大年龄？',
    receivedAt: '2026-08-06T08:00:00Z',
    source: 'MANUAL'
  }]
}

describe('human-in-loop reply draft state machine', () => {
  beforeEach(() => { setActivePinia(createPinia()) })

  it('moves a received message through generation, review, edit and acceptance', () => {
    const store = useHumanLoopWorkspaceStore()
    store.installConversations([seed])

    expect(store.activeDraft?.state).toBe('MESSAGE_RECEIVED')
    expect(store.agentStatus).toBe('BUSY')
    expect(store.activeConversation?.status).toBe('PROCESSING')
    store.beginUnderstanding()
    store.beginGenerating()
    store.setDraftReady({
      answer: '建议 5 岁以上使用。',
      requestId: 'request-1',
      action: 'CONTROLLED_ANSWER',
      riskLevel: 'LOW',
      citations: [],
      warnings: [],
      requiredFields: []
    })
    expect(store.activeDraft?.state).toBe('DRAFT_READY')
    store.beginHumanReview()
    store.beginEditing()
    store.editDraft('建议 5 岁以上使用，并由家长陪同。')
    store.acceptDraft()

    expect(store.activeDraft).toMatchObject({
      state: 'ACCEPTED',
      decisionState: 'APPROVED',
      editedAnswer: '建议 5 岁以上使用，并由家长陪同。'
    })
    expect(store.activeConversation?.status).toBe('WAITING_REPLY')
    store.completeConversation()
    expect(store.activeConversation?.status).toBe('COMPLETED')
    store.reopenConversation()
    expect(store.activeConversation?.status).toBe('PROCESSING')
  })

  it('expires the old draft as soon as a new customer message arrives', () => {
    const store = useHumanLoopWorkspaceStore()
    store.installConversations([seed])
    store.beginUnderstanding()
    store.beginGenerating()

    store.receiveMessage({
      messageId: 'message-2',
      conversationId: 'conversation-1',
      customerLabel: '客户 A01',
      content: '材质是什么？',
      receivedAt: '2026-08-06T08:01:00Z',
      source: 'MANUAL'
    })

    expect(store.draftHistory.at(-1)?.state).toBe('EXPIRED')
    expect(store.activeDraft).toMatchObject({ messageId: 'message-2', state: 'MESSAGE_RECEIVED' })
  })

  it('rejects illegal transitions and records a rejected human decision', () => {
    const store = useHumanLoopWorkspaceStore()
    store.installConversations([seed])
    expect(() => store.beginGenerating()).toThrow('不允许从 MESSAGE_RECEIVED 转换到 GENERATING')

    store.beginUnderstanding()
    store.beginGenerating()
    store.setDraftReady({
      answer: '知识不足，建议转人工。', requestId: null, action: 'TRANSFER_HUMAN',
      riskLevel: 'MEDIUM', citations: [], warnings: [], requiredFields: []
    })
    store.beginHumanReview()
    store.rejectDraft()

    expect(store.activeDraft).toMatchObject({ state: 'EXPIRED', decisionState: 'REJECTED' })
    expect(store.activeConversation?.status).toBe('PROCESSING')
  })

  it('derives ONLINE, BUSY and OFFLINE from availability and processing work', () => {
    const store = useHumanLoopWorkspaceStore()
    expect(store.agentStatus).toBe('ONLINE')
    store.installConversations([seed])
    expect(store.agentStatus).toBe('BUSY')
    store.setAgentAvailability(false)
    expect(store.agentStatus).toBe('OFFLINE')
    store.setAgentAvailability(true)
    expect(store.agentStatus).toBe('BUSY')
  })
})
