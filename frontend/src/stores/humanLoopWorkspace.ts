import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import type { RagAction, RagCitation, RiskLevel } from '@/api/ragTypes'
import type {
  ChannelConversationSeed,
  ChannelMessageEnvelope,
  ChannelMessageSource
} from '@/workspace/channelMessageAdapter'
import type { AgentStatus, ConversationStatus } from '@/workspace/customerSession'

export const REPLY_DRAFT_STATES = [
  'MESSAGE_RECEIVED',
  'UNDERSTANDING',
  'GENERATING',
  'DRAFT_READY',
  'HUMAN_REVIEW',
  'EDITED',
  'ACCEPTED',
  'EXPIRED'
] as const

export type ReplyDraftState = (typeof REPLY_DRAFT_STATES)[number]
export type DecisionReviewState = 'WAITING_HUMAN' | 'APPROVED' | 'REJECTED'
export type ReplyDraftSource = 'AI' | 'MANUAL'

export interface WorkspaceMessage extends ChannelMessageEnvelope {
  direction: 'INBOUND' | 'OUTBOUND_HISTORY' | 'OUTBOUND_DRAFT'
}

export interface WorkspaceConversation {
  conversationId: string
  customerLabel: string
  customerReference?: string
  unreadCount: number
  source: ChannelMessageSource
  status: ConversationStatus
  hostState?: string | null
  processingStage?: string | null
  riskLevel?: RiskLevel | null
  qualityStatus?: string | null
  policyMode?: 'MANUAL_CONFIRM' | 'AUTO_LOW_RISK' | 'AUTO_ALL_MESSAGES_V1' | null
  requiresHuman?: boolean
  attentionLevel?: 'HUMAN_REQUIRED' | 'UNANSWERED' | 'NONE'
  autoReplyRunning?: boolean
  autoReplyReceiptId?: string | null
  preparationId?: string | null
  traceId?: string | null
  messages: WorkspaceMessage[]
}

export interface ReplyDraft {
  draftId: string
  conversationId: string
  messageId: string
  state: ReplyDraftState
  decisionState: DecisionReviewState
  replySource: ReplyDraftSource | null
  originalAnswer: string
  editedAnswer: string
  requestId: string | null
  decisionId: string | null
  action: RagAction | null
  riskLevel: RiskLevel | null
  citations: RagCitation[]
  warnings: string[]
  requiredFields: string[]
  hostState: string | null
  qualityStatus: string | null
  policyMode: 'MANUAL_CONFIRM' | 'AUTO_LOW_RISK' | 'AUTO_ALL_MESSAGES_V1' | null
  preparationId: string | null
  traceId: string | null
  createdAt: string
  updatedAt: string
}

const TRANSITIONS: Record<ReplyDraftState, readonly ReplyDraftState[]> = {
  MESSAGE_RECEIVED: ['UNDERSTANDING', 'EDITED', 'EXPIRED'],
  UNDERSTANDING: ['GENERATING', 'EXPIRED'],
  GENERATING: ['DRAFT_READY', 'EXPIRED'],
  DRAFT_READY: ['HUMAN_REVIEW', 'EXPIRED'],
  HUMAN_REVIEW: ['EDITED', 'ACCEPTED', 'EXPIRED'],
  EDITED: ['EDITED', 'ACCEPTED', 'EXPIRED'],
  ACCEPTED: ['EXPIRED'],
  EXPIRED: ['EDITED']
}

const createDraftId = (): string => {
  const suffix = typeof globalThis.crypto?.randomUUID === 'function'
    ? globalThis.crypto.randomUUID()
    : `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`
  return `draft-${suffix}`
}

const nowIso = (): string => new Date().toISOString()

export const useHumanLoopWorkspaceStore = defineStore('human-loop-workspace', () => {
  const conversations = ref<WorkspaceConversation[]>([])
  const activeConversationId = ref('')
  const activeDraft = ref<ReplyDraft | null>(null)
  const draftHistory = ref<ReplyDraft[]>([])
  const agentAvailable = ref(true)

  const activeConversation = computed(() =>
    conversations.value.find((item) => item.conversationId === activeConversationId.value) ?? null
  )

  const latestInboundMessage = computed(() => {
    const messages = activeConversation.value?.messages ?? []
    return [...messages].reverse().find((message) => message.direction === 'INBOUND') ?? null
  })

  const agentStatus = computed<AgentStatus>(() => {
    if (!agentAvailable.value) return 'OFFLINE'
    return conversations.value.some((item) => item.status === 'PROCESSING') ? 'BUSY' : 'ONLINE'
  })

  const conversationCounts = computed<Record<ConversationStatus, number>>(() => ({
    NEW: conversations.value.filter((item) => item.status === 'NEW').length,
    PROCESSING: conversations.value.filter((item) => item.status === 'PROCESSING').length,
    WAITING_REPLY: conversations.value.filter((item) => item.status === 'WAITING_REPLY').length,
    COMPLETED: conversations.value.filter((item) => item.status === 'COMPLETED').length
  }))

  function installConversations(seeds: ChannelConversationSeed[]): void {
    conversations.value = seeds.map((seed) => ({
      conversationId: seed.conversationId,
      customerLabel: seed.customerLabel,
      customerReference: seed.customerReference,
      unreadCount: seed.unreadCount,
      source: seed.source,
      status: 'NEW',
      hostState: seed.state,
      processingStage: seed.processingStage,
      riskLevel: seed.riskLevel,
      qualityStatus: seed.qualityStatus,
      policyMode: seed.policyMode,
      requiresHuman: seed.requiresHuman === true,
      attentionLevel: seed.attentionLevel ?? 'UNANSWERED',
      autoReplyRunning: seed.autoReplyRunning === true,
      autoReplyReceiptId: seed.autoReplyReceiptId,
      preparationId: seed.preparationId,
      traceId: seed.traceId,
      messages: seed.messages.map((message) => ({
        ...message,
        direction: message.senderRole === 'AGENT' ? 'OUTBOUND_HISTORY' : 'INBOUND'
      }))
    }))
    if (!activeConversationId.value && conversations.value.length > 0) {
      activeConversationId.value = conversations.value[0].conversationId
      conversations.value[0].status = 'PROCESSING'
      conversations.value[0].unreadCount = 0
      createDraftForLatestMessage()
    }
  }

  function addConversation(seed: ChannelConversationSeed, select = true): void {
    const conversation: WorkspaceConversation = {
      conversationId: seed.conversationId,
      customerLabel: seed.customerLabel,
      customerReference: seed.customerReference,
      unreadCount: seed.unreadCount,
      source: seed.source,
      status: 'NEW',
      hostState: seed.state,
      processingStage: seed.processingStage,
      riskLevel: seed.riskLevel,
      qualityStatus: seed.qualityStatus,
      policyMode: seed.policyMode,
      requiresHuman: seed.requiresHuman === true,
      attentionLevel: seed.attentionLevel ?? 'UNANSWERED',
      autoReplyRunning: seed.autoReplyRunning === true,
      autoReplyReceiptId: seed.autoReplyReceiptId,
      preparationId: seed.preparationId,
      traceId: seed.traceId,
      messages: seed.messages.map((message) => ({
        ...message,
        direction: message.senderRole === 'AGENT' ? 'OUTBOUND_HISTORY' : 'INBOUND'
      }))
    }
    conversations.value.unshift(conversation)
    if (select) selectConversation(conversation.conversationId)
  }

  function selectConversation(conversationId: string): void {
    const conversation = conversations.value.find((item) => item.conversationId === conversationId)
    if (!conversation) throw new Error('会话不存在')
    if (activeConversationId.value !== conversationId) archiveActiveDraft()
    activeConversationId.value = conversationId
    conversation.unreadCount = 0
    if (conversation.status === 'NEW') conversation.status = 'PROCESSING'
    createDraftForLatestMessage()
  }

  function receiveMessage(message: ChannelMessageEnvelope): void {
    const conversation = conversations.value.find(
      (item) => item.conversationId === message.conversationId
    )
    if (!conversation) throw new Error('消息对应的会话不存在')

    if (message.senderRole === 'AGENT') {
      conversation.messages.push({ ...message, direction: 'OUTBOUND_HISTORY' })
      return
    }

    const isActive = activeConversationId.value === message.conversationId
    if (isActive && activeDraft.value?.conversationId === message.conversationId) {
      archiveActiveDraft()
    }
    conversation.messages.push({ ...message, direction: 'INBOUND' })
    conversation.unreadCount += 1
    conversation.status = 'NEW'
    if (!isActive) return
    activeConversationId.value = message.conversationId
    conversation.unreadCount = 0
    conversation.status = 'PROCESSING'
    createDraftForMessage(message)
  }

  function setAgentAvailability(online: boolean): void {
    agentAvailable.value = online
  }

  function beginUnderstanding(): void {
    transition('UNDERSTANDING')
  }

  function beginGenerating(): void {
    transition('GENERATING')
  }

  function setDraftReady(payload: {
    answer: string
    requestId: string | null
    decisionId?: string | null
    action: RagAction | null
    riskLevel: RiskLevel | null
    citations: RagCitation[]
    warnings: string[]
    requiredFields: string[]
    hostState?: string | null
    qualityStatus?: string | null
    policyMode?: 'MANUAL_CONFIRM' | 'AUTO_LOW_RISK' | 'AUTO_ALL_MESSAGES_V1' | null
    preparationId?: string | null
    traceId?: string | null
  }): void {
    transition('DRAFT_READY')
    if (!activeDraft.value) return
    activeDraft.value.originalAnswer = payload.answer
    activeDraft.value.editedAnswer = payload.answer
    activeDraft.value.replySource = 'AI'
    activeDraft.value.requestId = payload.requestId
    activeDraft.value.decisionId = payload.decisionId ?? null
    activeDraft.value.action = payload.action
    activeDraft.value.riskLevel = payload.riskLevel
    activeDraft.value.citations = payload.citations
    activeDraft.value.warnings = payload.warnings
    activeDraft.value.requiredFields = payload.requiredFields
    activeDraft.value.hostState = payload.hostState ?? null
    activeDraft.value.qualityStatus = payload.qualityStatus ?? null
    activeDraft.value.policyMode = payload.policyMode ?? null
    activeDraft.value.preparationId = payload.preparationId ?? null
    activeDraft.value.traceId = payload.traceId ?? null
    activeDraft.value.updatedAt = nowIso()
  }

  function beginHumanReview(): void {
    transition('HUMAN_REVIEW')
  }

  function beginEditing(): void {
    if (!activeDraft.value) throw new Error('当前没有可编辑的草稿')
    if (activeDraft.value.state !== 'HUMAN_REVIEW') throw new Error('当前草稿不允许进入修改')
    transition('EDITED')
  }

  function beginManualReply(answer: string): void {
    if (!activeDraft.value) throw new Error('当前没有可编辑的回复草稿')
    if (!['MESSAGE_RECEIVED', 'EXPIRED'].includes(activeDraft.value.state)) {
      throw new Error('当前草稿不允许切换为人工回复')
    }
    transition('EDITED')
    activeDraft.value.replySource = 'MANUAL'
    activeDraft.value.originalAnswer = ''
    activeDraft.value.editedAnswer = answer
    activeDraft.value.requestId = null
    activeDraft.value.decisionId = null
    activeDraft.value.action = null
    activeDraft.value.riskLevel = null
    activeDraft.value.citations = []
    activeDraft.value.warnings = []
    activeDraft.value.requiredFields = []
    activeDraft.value.hostState = null
    activeDraft.value.qualityStatus = null
    activeDraft.value.policyMode = null
    activeDraft.value.preparationId = null
    activeDraft.value.traceId = null
    activeDraft.value.updatedAt = nowIso()
  }

  function editDraft(answer: string): void {
    if (!activeDraft.value) throw new Error('当前没有可编辑的草稿')
    if (activeDraft.value.state !== 'EDITED') throw new Error('请先选择修改回复')
    activeDraft.value.editedAnswer = answer
    activeDraft.value.updatedAt = nowIso()
  }

  function acceptDraft(): void {
    if (!activeDraft.value) throw new Error('当前没有可采用的草稿')
    transition('ACCEPTED')
    activeDraft.value.decisionState = 'APPROVED'
    activeDraft.value.updatedAt = nowIso()
    const conversation = activeConversation.value
    if (conversation) conversation.status = 'WAITING_REPLY'
  }

  function rejectDraft(): void {
    if (!activeDraft.value) throw new Error('当前没有可拒绝的草稿')
    if (!['HUMAN_REVIEW', 'EDITED'].includes(activeDraft.value.state)) {
      throw new Error('当前草稿不允许拒绝')
    }
    activeDraft.value.decisionState = 'REJECTED'
    transition('EXPIRED')
    const conversation = activeConversation.value
    if (conversation) conversation.status = 'PROCESSING'
  }

  function completeConversation(): void {
    const conversation = activeConversation.value
    if (!conversation) throw new Error('当前没有会话')
    if (conversation.status !== 'WAITING_REPLY') {
      throw new Error('只有待人工发送的会话可以标记完成')
    }
    conversation.status = 'COMPLETED'
  }

  function reopenConversation(): void {
    const conversation = activeConversation.value
    if (!conversation) throw new Error('当前没有会话')
    if (conversation.status !== 'COMPLETED') throw new Error('当前会话尚未完成')
    conversation.status = 'PROCESSING'
    if (!activeDraft.value || activeDraft.value.state === 'EXPIRED') createDraftForLatestMessage()
  }

  function restartDraft(): void {
    const message = latestInboundMessage.value
    if (!message) throw new Error('当前会话没有客户消息')
    archiveActiveDraft()
    createDraftForMessage(message)
  }

  function expireDraft(): void {
    archiveActiveDraft()
  }

  function markDraftExpired(): void {
    if (activeDraft.value?.state !== 'EXPIRED') transition('EXPIRED')
  }

  function createDraftForLatestMessage(): void {
    const message = latestInboundMessage.value
    if (message) createDraftForMessage(message)
  }

  function createDraftForMessage(message: WorkspaceMessage | ChannelMessageEnvelope): void {
    const createdAt = nowIso()
    activeDraft.value = {
      draftId: createDraftId(),
      conversationId: message.conversationId,
      messageId: message.messageId,
      state: 'MESSAGE_RECEIVED',
      decisionState: 'WAITING_HUMAN',
      replySource: null,
      originalAnswer: '',
      editedAnswer: '',
      requestId: null,
      decisionId: null,
      action: null,
      riskLevel: null,
      citations: [],
      warnings: [],
      requiredFields: [],
      hostState: null,
      qualityStatus: null,
      policyMode: null,
      preparationId: null,
      traceId: null,
      createdAt,
      updatedAt: createdAt
    }
  }

  function archiveActiveDraft(): void {
    if (!activeDraft.value) return
    if (activeDraft.value.state !== 'EXPIRED') {
      if (!TRANSITIONS[activeDraft.value.state].includes('EXPIRED')) {
        throw new Error(`草稿状态 ${activeDraft.value.state} 不能失效`)
      }
      activeDraft.value.state = 'EXPIRED'
      activeDraft.value.updatedAt = nowIso()
    }
    draftHistory.value.push({
      ...activeDraft.value,
      citations: activeDraft.value.citations.map((citation) => ({
        ...citation,
        sourceIds: [...citation.sourceIds]
      })),
      warnings: [...activeDraft.value.warnings],
      requiredFields: [...activeDraft.value.requiredFields]
    })
    activeDraft.value = null
  }

  function transition(next: ReplyDraftState): void {
    if (!activeDraft.value) throw new Error('当前没有回复草稿')
    const current = activeDraft.value.state
    if (!TRANSITIONS[current].includes(next)) {
      throw new Error(`不允许从 ${current} 转换到 ${next}`)
    }
    activeDraft.value.state = next
    activeDraft.value.updatedAt = nowIso()
  }

  return {
    conversations,
    activeConversationId,
    activeConversation,
    activeDraft,
    draftHistory,
    latestInboundMessage,
    agentStatus,
    conversationCounts,
    installConversations,
    addConversation,
    selectConversation,
    receiveMessage,
    setAgentAvailability,
    beginUnderstanding,
    beginGenerating,
    setDraftReady,
    beginHumanReview,
    beginEditing,
    beginManualReply,
    editDraft,
    acceptDraft,
    rejectDraft,
    completeConversation,
    reopenConversation,
    restartDraft,
    expireDraft,
    markDraftExpired
  }
})
