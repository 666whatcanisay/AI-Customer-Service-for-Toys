import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { SystemStatusKey } from '@/workspace/systemStatus'
import { TesterIdentityKey } from '@/workspace/testerIdentity'
import WorkspaceHome from './WorkspaceHome.vue'

describe('WorkspaceHome', () => {
  it('shows all modules, their lifecycle status and the main AI entry', () => {
    const wrapper = mount(WorkspaceHome, {
      global: {
        provide: {
          [TesterIdentityKey as symbol]: {
            identity: ref({ reporterId: 'TESTER-ONE', reporterName: '小木', defaultStoreCode: 'PDD-SM' }),
            save: vi.fn(), reload: vi.fn()
          },
          [SystemStatusKey as symbol]: {
            aiReady: ref(true), dataReady: ref(false), loading: ref(false),
            aiError: ref(''), dataError: ref('数据服务待连接'), refresh: vi.fn()
          }
        },
        stubs: { RouterLink: { props: ['to'], template: '<a :href="String(to)"><slot /></a>' } }
      }
    })

    expect(wrapper.findAll('[data-testid="module-card"]')).toHaveLength(12)
    expect(wrapper.text()).toContain('AI 客服')
    expect(wrapper.text()).toContain('意见与建议')
    expect(wrapper.text()).toContain('售后中心')
    expect(wrapper.text()).toContain('开发中')
    expect(wrapper.text()).toContain('规划中')
    expect(wrapper.get('[data-testid="enter-ai-chat"]').attributes('href')).toBe('/ai-chat')
  })
})
