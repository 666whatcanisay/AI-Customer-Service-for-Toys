import { describe, expect, it } from 'vitest'

import { displayAuditAction, displayCapability, displayStatus } from '../src/presentation'

describe('Chinese operation presentation', () => {
  it('converts transport enums to business-facing Chinese labels', () => {
    expect(displayStatus('READY_FOR_REVIEW')).toBe('待审核')
    expect(displayStatus('MISSING_INFO')).toBe('信息缺失')
    expect(displayStatus('EVALUATED')).toBe('已评测')
  })

  it('does not expose trial capability or audit codes as primary UI labels', () => {
    expect(displayCapability('audit.read')).toBe('查看审计记录')
    expect(displayAuditAction('EXPERIENCE_CASE_REVIEW')).toBe('审核客服案例')
  })
})
