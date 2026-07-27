import { describe, expect, it } from 'vitest'

import { displayStatus } from '../src/presentation'

describe('displayStatus', () => {
  it('keeps API enum values in transport while showing pilot operators Chinese business labels', () => {
    expect(displayStatus('EDITED_ADOPTED')).toBe('编辑后采用')
    expect(displayStatus('MISSING_INFO')).toBe('信息缺失')
    expect(displayStatus('UNKNOWN_API_VALUE')).toBe('UNKNOWN_API_VALUE')
    expect(displayStatus(null)).toBe('未设置')
  })
})
