import { afterEach, describe, expect, it, vi } from 'vitest'

import { HttpChannelAgentMessageAdapter, InMemoryChannelMessageAdapter } from './channelMessageAdapter'

afterEach(() => {
  vi.unstubAllGlobals()
})

const safeChannelAgentFeed = () => ({
  schemaVersion: 'channel-agent-workspace-feed.v1',
  conversations: [],
  reply: null,
  safety: {
    readOnly: true,
    autoReply: false,
    realSend: false,
    browserWriteOperations: 0,
    executionCount: 0,
    receiptCount: 0,
    sendCount: 0
  }
})

describe('HttpChannelAgentMessageAdapter', () => {
  it('accepts the canonical safe empty feed used before the first real message', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => safeChannelAgentFeed()
    }))
    await expect(new HttpChannelAgentMessageAdapter().listConversations()).resolves.toEqual([])
  })

  it('fails closed if any automatic-send safety fact becomes unsafe', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...safeChannelAgentFeed(),
        safety: { ...safeChannelAgentFeed().safety, autoReply: true }
      })
    }))
    await expect(new HttpChannelAgentMessageAdapter().listConversations())
      .rejects.toThrow('Channel Agent 会话安全校验失败')
  })

  it('accepts v2 low-risk automatic preparation and resolves the reply per conversation', async () => {
    const reply = {
      conversationId: 'conversation-b', customerReference: `sha256:${'b'.repeat(64)}`,
      messageId: 'message-b', decisionId: 'decision-b', answer: 'reply-b', requestId: 'request-b',
      action: 'CONTROLLED_ANSWER', riskLevel: 'LOW', citations: [], warnings: [], requiredFields: [],
      state: 'EXECUTION_PREPARED', qualityStatus: 'PASS', policyMode: 'AUTO_LOW_RISK',
      preparationId: `execution-preparation:${'c'.repeat(64)}`, traceId: `trace:${'d'.repeat(64)}`
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...safeChannelAgentFeed(),
        schemaVersion: 'channel-agent-workspace-feed.v2',
        conversations: [
          { conversationId: 'conversation-a', customerLabel: '客户 A', unreadCount: 0, source: 'CHANNEL_AGENT', messages: [] },
          { conversationId: 'conversation-b', customerLabel: '客户 B', unreadCount: 1, source: 'CHANNEL_AGENT', messages: [], reply }
        ],
        replies: { 'conversation-b': reply },
        safety: { ...safeChannelAgentFeed().safety, autoReply: true, executionPrepared: true }
      })
    }))
    const adapter = new HttpChannelAgentMessageAdapter()
    await adapter.listConversations()

    await expect(adapter.latestReply('conversation-a')).resolves.toBeNull()
    await expect(adapter.latestReply('conversation-b')).resolves.toMatchObject({
      answer: 'reply-b', policyMode: 'AUTO_LOW_RISK', state: 'EXECUTION_PREPARED'
    })
  })

  it('accepts a truthful v2 production-auto feed and exposes the running state', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...safeChannelAgentFeed(),
        schemaVersion: 'channel-agent-workspace-feed.v2',
        conversations: [{
          conversationId: 'conversation-auto', customerLabel: 'customer-auto', unreadCount: 1,
          source: 'CHANNEL_AGENT', messages: [], attentionLevel: 'UNANSWERED'
        }],
        safety: {
          ...safeChannelAgentFeed().safety,
          autoReply: true,
          realSend: true
        }
      })
    }))

    await expect(new HttpChannelAgentMessageAdapter().listConversations())
      .resolves.toEqual([
        expect.objectContaining({
          conversationId: 'conversation-auto',
          autoReplyRunning: true,
          attentionLevel: 'UNANSWERED'
        })
      ])
  })

  it('uses the selected conversation product context and never another conversation fallback', async () => {
    const reply = {
      conversationId: 'conversation-b', customerReference: `sha256:${'b'.repeat(64)}`,
      messageId: 'message-b', decisionId: 'decision-b', answer: 'reply-b', requestId: 'request-b',
      action: 'CONTROLLED_ANSWER', riskLevel: 'LOW', citations: [], warnings: [], requiredFields: []
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...safeChannelAgentFeed(),
        schemaVersion: 'channel-agent-workspace-feed.v2',
        conversations: [{
          conversationId: 'conversation-b', customerLabel: '客户 B', unreadCount: 1,
          source: 'CHANNEL_AGENT', messages: [], reply,
          productContext: {
            productReference: 'product-b', productName: '商品 B', applicableAge: '6岁以上'
          }
        }],
        replies: { 'conversation-b': reply },
        productContext: {
          productReference: 'wrong-global', productName: '错误商品', applicableAge: '3岁以上'
        }
      })
    }))
    const adapter = new HttpChannelAgentMessageAdapter()
    await adapter.listConversations()
    await expect(adapter.latestReply('conversation-b')).resolves.toMatchObject({
      product: { productReference: 'product-b', productName: '商品 B', applicableAge: '6岁以上' }
    })
  })

  it('keeps an identified product when applicable age is absent', async () => {
    const reply = {
      conversationId: 'conversation-b', customerReference: `sha256:${'b'.repeat(64)}`,
      messageId: 'message-b', decisionId: 'decision-b', answer: 'reply-b', requestId: 'request-b',
      action: 'CONTROLLED_ANSWER', riskLevel: 'LOW', citations: [], warnings: [], requiredFields: []
    }
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        ...safeChannelAgentFeed(),
        schemaVersion: 'channel-agent-workspace-feed.v2',
        conversations: [{
          conversationId: 'conversation-b', customerLabel: '客户 B', unreadCount: 1,
          source: 'CHANNEL_AGENT', messages: [], reply,
          productContext: {
            productReference: 'product-b', productName: '商品 B', applicableAge: null
          }
        }],
        replies: { 'conversation-b': reply }
      })
    }))
    const adapter = new HttpChannelAgentMessageAdapter()
    await adapter.listConversations()
    await expect(adapter.latestReply('conversation-b')).resolves.toMatchObject({
      product: { productReference: 'product-b', productName: '商品 B', applicableAge: null }
    })
  })

  it('persists a read cursor through the local desktop endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)
    await new HttpChannelAgentMessageAdapter().markRead('conversation/a')
    expect(fetchMock).toHaveBeenCalledWith(
      '/local-api/v1/conversations/conversation%2Fa/read',
      expect.objectContaining({ method: 'POST', credentials: 'same-origin' })
    )
  })

  it('persists a human replied confirmation through the local desktop endpoint', async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({}) })
    vi.stubGlobal('fetch', fetchMock)
    await new HttpChannelAgentMessageAdapter().markReplied('conversation/a')
    expect(fetchMock).toHaveBeenCalledWith(
      '/local-api/v1/conversations/conversation%2Fa/replied',
      expect.objectContaining({
        method: 'POST',
        credentials: 'same-origin',
        headers: expect.objectContaining({
          'X-Channel-Agent-Intent': 'HUMAN_CONFIRMED_CONVERSATION_REPLIED'
        })
      })
    )
  })
})

describe('InMemoryChannelMessageAdapter', () => {
  it('starts empty and does not invent a real channel conversation', async () => {
    const adapter = new InMemoryChannelMessageAdapter()
    const conversations = await adapter.listConversations()

    expect(conversations).toEqual([])
  })

  it('creates and appends a page-memory manual conversation', async () => {
    const adapter = new InMemoryChannelMessageAdapter()
    const conversation = await adapter.createManualConversation('客户 A01', '适合几岁？')
    const message = await adapter.receiveManualMessage(conversation.conversationId, '还有其他注意事项吗？')

    expect(message).toMatchObject({
      conversationId: conversation.conversationId,
      content: '还有其他注意事项吗？',
      source: 'MANUAL'
    })
    expect(await adapter.listConversations()).toHaveLength(1)
  })

  it('requires a de-identified customer label for a new manual conversation', async () => {
    const adapter = new InMemoryChannelMessageAdapter()
    await expect(adapter.createManualConversation('  ', '适合几岁？'))
      .rejects.toThrow('请填写去标识化客户代号')
    await expect(adapter.createManualConversation('客户 13800138000', '适合几岁？'))
      .rejects.toThrow('客户代号不能包含')
  })

  it('removes common direct identifiers before keeping a manual message in page memory', async () => {
    const adapter = new InMemoryChannelMessageAdapter()
    const conversation = await adapter.createManualConversation(
      '客户 A01',
      '手机号13800138000，邮箱 buyer@example.com，订单1234567890'
    )
    expect(conversation.messages[0].content).toContain('[手机号已移除]')
    expect(conversation.messages[0].content).toContain('[邮箱已移除]')
    expect(conversation.messages[0].content).toContain('[长编号已移除]')
    expect(conversation.messages[0].content).not.toContain('13800138000')
  })
})
