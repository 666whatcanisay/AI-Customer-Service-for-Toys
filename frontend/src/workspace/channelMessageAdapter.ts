export type ChannelMessageSource = 'MANUAL' | 'VALIDATION_FIXTURE' | 'CHANNEL_AGENT'

export interface ChannelMessageEnvelope {
  messageId: string
  conversationId: string
  customerLabel: string
  content: string
  receivedAt: string
  source: ChannelMessageSource
  senderRole?: 'CUSTOMER' | 'AGENT'
}

export interface ChannelConversationSeed {
  conversationId: string
  customerLabel: string
  unreadCount: number
  source: ChannelMessageSource
  messages: ChannelMessageEnvelope[]
}

export interface ChannelAgentReplySeed {
  conversationId: string
  messageId: string
  decisionId: string
  answer: string
  requestId: string | null
  action: 'DIRECT_ANSWER' | 'CONTROLLED_ANSWER' | 'ASK_CLARIFY' | 'REQUIRE_LOOKUP' | 'TRANSFER_HUMAN' | 'REFUSE'
  riskLevel: 'LOW' | 'MEDIUM' | 'HIGH'
  citations: Array<{
    file: string
    page: number | null
    chunkId: string | null
    summary: string
    distance: number | null
    knowledgeVersion: string | null
    sourceIds: string[]
    productId: string | null
    skuId: string | null
  }>
  warnings: string[]
  requiredFields: string[]
  product: {
    productReference: string
    productName: string
    applicableAge: string
  } | null
}

export interface ChannelMessageAdapter {
  listConversations(): Promise<ChannelConversationSeed[]>
  latestReply(): Promise<ChannelAgentReplySeed | null>
  createManualConversation(customerLabel: string, content: string): Promise<ChannelConversationSeed>
  receiveManualMessage(conversationId: string, content: string): Promise<ChannelMessageEnvelope>
}

type ChannelAgentFeed = {
  schemaVersion: 'channel-agent-workspace-feed.v1'
  conversations: ChannelConversationSeed[]
  reply: Omit<ChannelAgentReplySeed, 'product'> | null
  productContext?: {
    productReference?: string
    productName?: string
    applicableAge?: string
  }
  safety: {
    readOnly: true
    autoReply: false
    realSend: false
    browserWriteOperations: 0
    executionCount: 0
    receiptCount: 0
    sendCount: 0
  }
}

const CHANNEL_AGENT_FEED_URL = '/channel-agent-api/assistant-feed.json'

const isChannelAgentFeed = (value: unknown): value is ChannelAgentFeed => {
  if (!value || typeof value !== 'object') return false
  const feed = value as Partial<ChannelAgentFeed>
  return feed.schemaVersion === 'channel-agent-workspace-feed.v1'
    && Array.isArray(feed.conversations)
    && feed.safety?.readOnly === true
    && feed.safety.autoReply === false
    && feed.safety.realSend === false
    && feed.safety.browserWriteOperations === 0
    && feed.safety.executionCount === 0
    && feed.safety.receiptCount === 0
    && feed.safety.sendCount === 0
}

export class HttpChannelAgentMessageAdapter implements ChannelMessageAdapter {
  private feed: ChannelAgentFeed | null = null

  async listConversations(): Promise<ChannelConversationSeed[]> {
    const response = await fetch(CHANNEL_AGENT_FEED_URL, {
      method: 'GET',
      cache: 'no-store',
      credentials: 'same-origin',
      headers: { Accept: 'application/json' }
    })
    if (!response.ok) throw new Error('Channel Agent 真实会话暂时不可用')
    const payload: unknown = await response.json()
    if (!isChannelAgentFeed(payload)) throw new Error('Channel Agent 会话安全校验失败')
    this.feed = payload
    return structuredClone(payload.conversations)
  }

  async latestReply(): Promise<ChannelAgentReplySeed | null> {
    if (!this.feed?.reply?.answer) return null
    const product = this.feed.productContext
    return structuredClone({
      ...this.feed.reply,
      product: product?.productReference && product.productName && product.applicableAge
        ? {
            productReference: product.productReference,
            productName: product.productName,
            applicableAge: product.applicableAge
          }
        : null
    })
  }

  async createManualConversation(): Promise<ChannelConversationSeed> {
    throw new Error('真实 Channel Agent 模式不使用手工模拟客户')
  }

  async receiveManualMessage(): Promise<ChannelMessageEnvelope> {
    throw new Error('真实 Channel Agent 模式不使用手工模拟客户')
  }
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

  async latestReply(): Promise<ChannelAgentReplySeed | null> {
    return null
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
  import.meta.env.MODE === 'test'
    ? new InMemoryChannelMessageAdapter(VALIDATION_CONVERSATIONS)
    : new HttpChannelAgentMessageAdapter()
