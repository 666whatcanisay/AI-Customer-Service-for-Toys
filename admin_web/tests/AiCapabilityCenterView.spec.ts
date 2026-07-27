import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import AiCapabilityCenterView from '../src/views/AiCapabilityCenterView.vue'
import { listAiModules } from '../src/api/client'

vi.mock('../src/api/client', () => ({ listAiModules: vi.fn() }))

const mockedModules = vi.mocked(listAiModules)

describe('AiCapabilityCenterView', () => {
  beforeEach(() => mockedModules.mockReset())

  it('renders returned A-line modules without creating online test controls', async () => {
    mockedModules.mockResolvedValue([{ id: 'answer', name: 'Answer module', status: 'READY', description: null, promptMetadata: null, recentEvaluations: [] }])
    const wrapper = mount(AiCapabilityCenterView)
    await flushPromises()

    expect(wrapper.text()).toContain('Answer module')
    expect(wrapper.find('button[disabled]').exists()).toBe(false)
  })
})
