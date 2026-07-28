import { describe, expect, it } from 'vitest'

import { displayStatus } from '../src/presentation'

describe('displayStatus', () => {
  it('keeps API enum values in transport while showing pilot operators Chinese business labels', () => {
    expect(displayStatus('EDITED_ADOPTED')).toBe('编辑后采用')
    expect(displayStatus('MISSING_INFO')).toBe('信息缺失')
    expect(displayStatus('RECEIVED')).toBe('已接收')
    expect(displayStatus('RECOGNIZED')).toBe('已识别，待审核')
    expect(displayStatus('REVIEWING')).toBe('审核中')
    expect(displayStatus('APPROVED_FOR_ANALYSIS')).toBe('已审核，待分析')
    expect(displayStatus('ANALYZING')).toBe('分析中')
    expect(displayStatus('ANALYZED')).toBe('已完成分析')
    expect(displayStatus('ANALYSIS_FAILED')).toBe('分析未完成')
    expect(displayStatus('REJECTED')).toBe('已拒绝')
    expect(displayStatus('UNKNOWN_API_VALUE')).toBe('UNKNOWN_API_VALUE')
    expect(displayStatus(null)).toBe('未设置')
  })
})
