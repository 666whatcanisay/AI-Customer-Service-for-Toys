import type { ExperienceCaseStatus } from '@/api/experienceCaseTypes'
import type { ExperienceCaseFeedbackType } from '@/api/experienceCaseTypes'

export const EXPERIENCE_CASE_STATUS_LABELS: Record<ExperienceCaseStatus, string> = {
  NEW: '新建',
  REVIEWING: '审核中',
  APPROVED: '已通过',
  REJECTED: '未通过'
}

export const EXPERIENCE_FEEDBACK_LABELS: Record<ExperienceCaseFeedbackType, string> = {
  ADOPTED: '采用 AI 建议',
  EDITED_ADOPTED: '修改后采用',
  CORRECTION: '人工纠正 AI 建议',
  ESCALATED: '需升级人工处理'
}
