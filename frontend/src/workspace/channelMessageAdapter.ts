export type ChannelMessageSource = 'MANUAL' | 'VALIDATION_FIXTURE' | 'CHANNEL_AGENT'

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
  createManualConversation(customerLabel: string, content: string): Promise<ChannelConversationSeed>
  receiveManualMessage(conversationId: string, content: string): Promise<ChannelMessageEnvelope>
}

const createId = (prefix: string): string => {
  const suffix = typeof globalThis.crypto?.randomUUID === 'function'
    ? globalThis.crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  return `${prefix}-${suffix}`
}

const nowIso = (): string => new Date().toISOString()
const emailPattern = /\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b/gi
const phonePattern = /(?:\+?86[- ]?)?1[3-9]\d{9}/g
const identityPattern = /\d{6}(?:19|20)\d{2}[01]\d[0-3]\d{4}[\dXx]/g
const longNumberPattern = /\d{8,}/g

export const redactManualMessageContent = (value: string): string => value
  .replace(emailPattern, '[邮箱已移除]')
  .replace(phonePattern, '[手机号已移除]')
  .replace(identityPattern, '[身份证号已移除]')
  .replace(longNumberPattern, '[长编号已移除]')
  .trim()

const hasSensitiveIdentifier = (value: string): boolean => {
  const redacted = redactManualMessageContent(value)
  return redacted !== value.trim()
}

const VALIDATION_CONVERSATIONS: ChannelConversationSeed[] = [
    {
      conversationId: 'validation-conversation-age',
      customerLabel: '客户 A17',
      unreadCount: 1,
      source: 'VALIDATION_FIXTURE',
      messages: [
        {
          messageId: 'validation-message-age',
          conversationId: 'validation-conversation-age',
          customerLabel: '客户 A17',
          content: '这款积木适合多大年龄？材质安全吗？',
          receivedAt: nowIso(),
          source: 'VALIDATION_FIXTURE'
        }
      ]
    },
    {
      conversationId: 'validation-conversation-play',
      customerLabel: '客户 B08',
      unreadCount: 1,
      source: 'VALIDATION_FIXTURE',
      messages: [
        {
          messageId: 'validation-message-play',
          conversationId: 'validation-conversation-play',
          customerLabel: '客户 B08',
          content: '这个商品怎么玩？需要大人陪同吗？',
          receivedAt: nowIso(),
          source: 'VALIDATION_FIXTURE'
        }
      ]
    }
]

/**
 * Manual intake is intentionally page-memory only. It does not claim a real
 * channel connection and never writes customer content to browser storage.
 */
export class InMemoryChannelMessageAdapter implements ChannelMessageAdapter {
  private readonly conversations: ChannelConversationSeed[]

  constructor(seeds: ChannelConversationSeed[] = []) {
    this.conversations = structuredClone(seeds)
  }

  async listConversations(): Promise<ChannelConversationSeed[]> {
    return structuredClone(this.conversations)
  }

  async createManualConversation(
    customerLabel: string,
    content: string
  ): Promise<ChannelConversationSeed> {
    const normalizedLabel = customerLabel.trim()
    const normalizedContent = redactManualMessageContent(content)
    if (!normalizedLabel) throw new Error('请填写去标识化客户代号')
    if (normalizedLabel.length > 32) throw new Error('客户代号不能超过32个字符')
    if (hasSensitiveIdentifier(normalizedLabel)) {
      throw new Error('客户代号不能包含手机号、邮箱、身份证号或长编号')
    }
    if (!normalizedContent) throw new Error('人工录入消息不能为空')
    if (normalizedContent.length > 300) throw new Error('人工录入消息不能超过300个字符')
    const conversationId = createId('manual-conversation')
    const message: ChannelMessageEnvelope = {
      messageId: createId('manual-message'),
      conversationId,
      customerLabel: normalizedLabel,
      content: normalizedContent,
      receivedAt: nowIso(),
      source: 'MANUAL'
    }
    const conversation: ChannelConversationSeed = {
      conversationId,
      customerLabel: normalizedLabel,
      unreadCount: 1,
      source: 'MANUAL',
      messages: [message]
    }
    this.conversations.unshift(conversation)
    return structuredClone(conversation)
  }

  async receiveManualMessage(conversationId: string, content: string): Promise<ChannelMessageEnvelope> {
    const conversation = this.conversations.find((item) => item.conversationId === conversationId)
    if (!conversation) throw new Error('人工会话不存在')
    const normalized = redactManualMessageContent(content)
    if (!normalized) throw new Error('人工录入消息不能为空')
    if (normalized.length > 300) throw new Error('人工录入消息不能超过300个字符')

    const message: ChannelMessageEnvelope = {
      messageId: createId('manual-message'),
      conversationId,
      customerLabel: conversation.customerLabel,
      content: normalized,
      receivedAt: nowIso(),
      source: 'MANUAL'
    }
    conversation.messages.push(message)
    conversation.unreadCount += 1
    return structuredClone(message)
  }
}

export const createWorkspaceMessageAdapter = (): ChannelMessageAdapter =>
  new InMemoryChannelMessageAdapter(import.meta.env.MODE === 'test' ? VALIDATION_CONVERSATIONS : [])
