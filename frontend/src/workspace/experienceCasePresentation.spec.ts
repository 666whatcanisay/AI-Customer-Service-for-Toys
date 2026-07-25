import { describe, expect, it } from 'vitest'
import { EXPERIENCE_CASE_STATUS_LABELS } from './experienceCasePresentation'

describe('experience case status presentation', () => {
  it('labels every C review status for the customer workspace', () => {
    expect(EXPERIENCE_CASE_STATUS_LABELS).toEqual({
      NEW: '新建',
      REVIEWING: '审核中',
      APPROVED: '已通过',
      REJECTED: '未通过'
    })
  })
})
