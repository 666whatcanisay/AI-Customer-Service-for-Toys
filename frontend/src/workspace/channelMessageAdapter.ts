export type ChannelMessageSource = 'MOCK' | 'CHANNEL_AGENT'

export interface ChannelMessageEnvelope {
  messageId: string
  conversationId: string
  customerLabel: string
  content: string
  receivedAt: string
  source: ChannelMessageSource
}

export interface ChannelConversationSeed {
  conversationId: string
  customerLabel: string
  unreadCount: number
  source: ChannelMessageSource
  messages: ChannelMessageEnvelope[]
}

export interface ChannelMessageAdapter {
  listConversations(): Promise<ChannelConversationSeed[]>
  receiveMockMessage(conversationId: string, content: string): Promise<ChannelMessageEnvelope>
}

const createId = (prefix: string): string => {
  const suffix = typeof globalThis.crypto?.randomUUID === 'function'
    ? globalThis.crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  return `${prefix}-${suffix}`
}

const nowIso = (): string => new Date().toISOString()

/**
 * The V1 workspace deliberately uses an in-memory source.  It proves the
 * human-in-the-loop product flow without importing Channel Engine code or
 * opening a real channel session.
 */
export class MockChannelMessageAdapter implements ChannelMessageAdapter {
  private readonly conversations: ChannelConversationSeed[] = [
    {
      conversationId: 'mock-conversation-age',
      customerLabel: '客户 A17',
      unreadCount: 1,
      source: 'MOCK',
      messages: [
        {
          messageId: 'mock-message-age',
          conversationId: 'mock-conversation-age',
          customerLabel: '客户 A17',
          content: '这款积木适合多大年龄？材质安全吗？',
          receivedAt: nowIso(),
          source: 'MOCK'
        }
      ]
    },
    {
      conversationId: 'mock-conversation-play',
      customerLabel: '客户 B08',
      unreadCount: 1,
      source: 'MOCK',
      messages: [
        {
          messageId: 'mock-message-play',
          conversationId: 'mock-conversation-play',
          customerLabel: '客户 B08',
          content: '这个商品怎么玩？需要大人陪同吗？',
          receivedAt: nowIso(),
          source: 'MOCK'
        }
      ]
    }
  ]

  async listConversations(): Promise<ChannelConversationSeed[]> {
    return structuredClone(this.conversations)
  }

  async receiveMockMessage(conversationId: string, content: string): Promise<ChannelMessageEnvelope> {
    const conversation = this.conversations.find((item) => item.conversationId === conversationId)
    if (!conversation) throw new Error('模拟会话不存在')
    const normalized = content.trim()
    if (!normalized) throw new Error('模拟客户消息不能为空')

    const message: ChannelMessageEnvelope = {
      messageId: createId('mock-message'),
      conversationId,
      customerLabel: conversation.customerLabel,
      content: normalized,
      receivedAt: nowIso(),
      source: 'MOCK'
    }
    conversation.messages.push(message)
    conversation.unreadCount += 1
    return structuredClone(message)
  }
}

