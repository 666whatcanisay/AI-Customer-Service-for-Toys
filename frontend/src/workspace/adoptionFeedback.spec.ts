import { describe, expect, it } from 'vitest'
import { NOT_ADOPTED_REASON_LABELS, NOT_ADOPTED_REASONS } from './adoptionFeedback'

describe('AI problem-feedback reason presentation', () => {
  it('uses the frozen cross-line reason set and labels', () => {
    expect(NOT_ADOPTED_REASONS).toEqual([
      'FACT_ERROR',
      'MISSING_INFO',
      'STYLE_ISSUE',
      'RISK_ISSUE',
      'OTHER'
    ])
    expect(NOT_ADOPTED_REASON_LABELS.RISK_ISSUE).toBe('风险问题')
  })
})
