import {
  AI_RESPONSE_FEEDBACK_TYPES,
  type AiResponseFeedbackType
} from '@/api/aiResponseFeedbackTypes'

export const NOT_ADOPTED_REASONS = AI_RESPONSE_FEEDBACK_TYPES

export type NotAdoptedReason = AiResponseFeedbackType

export const NOT_ADOPTED_REASON_LABELS: Record<NotAdoptedReason, string> = {
  FACT_ERROR: '事实错误',
  MISSING_INFO: '缺少信息',
  STYLE_ISSUE: '表达问题',
  RISK_ISSUE: '风险问题',
  OTHER: '其他'
}
