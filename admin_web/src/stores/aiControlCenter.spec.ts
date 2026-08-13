import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({
  getAiControlCenterOverview: vi.fn(),
  apiErrorMessage: vi.fn(() => 'unavailable'),
}))
vi.mock('../api/client', () => api)

import {
  aiControlCenterError,
  aiControlCenterOverview,
  loadAiControlCenterOverview,
} from './aiControlCenter'

describe('shared AI control center fact', () => {
  beforeEach(() => {
    aiControlCenterOverview.value = null
    aiControlCenterError.value = ''
    api.getAiControlCenterOverview.mockReset()
  })

  it('shares one in-flight request between header and status page consumers', async () => {
    let resolve!: (value: object) => void
    api.getAiControlCenterOverview.mockReturnValue(new Promise((done) => { resolve = done }))
    const header = loadAiControlCenterOverview()
    const page = loadAiControlCenterOverview()
    expect(api.getAiControlCenterOverview).toHaveBeenCalledTimes(1)
    resolve({ service: { status: 'RUNNING', ready: true, modelConfigured: true } })
    expect(await header).toBe(await page)
    expect(aiControlCenterOverview.value?.service.status).toBe('RUNNING')
  })
})
