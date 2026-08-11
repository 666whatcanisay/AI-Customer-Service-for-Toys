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
