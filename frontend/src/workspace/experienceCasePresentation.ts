import type { ExperienceCaseStatus } from '@/api/experienceCaseTypes'
import type { AdoptionType } from '@/api/ragTypes'

export const EXPERIENCE_CASE_STATUS_LABELS: Record<ExperienceCaseStatus, string> = {
  NEW: '新建',
  REVIEWING: '审核中',
  APPROVED: '已通过',
  REJECTED: '未通过'
}

export const EXPERIENCE_FEEDBACK_LABELS: Record<AdoptionType, string> = {
  DIRECT_ACCEPT: '直接采用',
  EDITED_ACCEPT: '修改后采用',
  REJECTED: '未采用'
}
