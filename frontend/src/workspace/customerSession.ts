export const AGENT_STATUSES = ['ONLINE', 'BUSY', 'OFFLINE'] as const
export const CONVERSATION_STATUSES = [
  'NEW',
  'PROCESSING',
  'WAITING_REPLY',
  'COMPLETED'
] as const

export type AgentStatus = (typeof AGENT_STATUSES)[number]
export type ConversationStatus = (typeof CONVERSATION_STATUSES)[number]

export const AGENT_STATUS_LABELS: Record<AgentStatus, string> = {
  ONLINE: '在线',
  BUSY: '处理中',
  OFFLINE: '离线'
}

export const CONVERSATION_STATUS_LABELS: Record<ConversationStatus, string> = {
  NEW: '新会话',
  PROCESSING: '处理中',
  WAITING_REPLY: '待人工发送',
  COMPLETED: '已完成'
}
