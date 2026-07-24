import type {
  SuggestionCategory,
  SuggestionFrequency,
  SuggestionUrgency
} from '@/api/suggestionTypes'

export const CATEGORY_LABELS: Record<SuggestionCategory, string> = {
  BUG: '问题反馈',
  IMPROVEMENT: '改进建议',
  NEW_FEATURE: '新功能建议',
  DATA_ISSUE: '数据问题',
  OTHER: '其他'
}

export const FREQUENCY_LABELS: Record<SuggestionFrequency, string> = {
  ONCE: '只出现一次',
  OCCASIONAL: '偶尔出现',
  FREQUENT: '经常出现',
  DAILY: '每天出现'
}

export const URGENCY_LABELS: Record<SuggestionUrgency, string> = {
  LOW: '不紧急',
  MEDIUM: '希望尽快处理',
  HIGH: '影响当前测试'
}

const STATUS_LABELS: Record<string, string> = {
  SUBMITTED: '已提交',
  OPEN: '待处理',
  REVIEWING: '处理中',
  IN_PROGRESS: '处理中',
  RESOLVED: '已处理',
  CLOSED: '已关闭',
  REJECTED: '暂不采纳'
}

export const suggestionStatusLabel = (status: string): string =>
  STATUS_LABELS[status.trim().toUpperCase()] ?? '状态待确认'
