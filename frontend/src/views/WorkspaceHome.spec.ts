import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { SystemStatusKey } from '@/workspace/systemStatus'
import { TesterIdentityKey } from '@/workspace/testerIdentity'
import WorkspaceHome from './WorkspaceHome.vue'

describe('WorkspaceHome', () => {
  it('shows the daily AI entry, real-workflow links and clearly planned modules', () => {
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

    expect(wrapper.findAll('[data-testid="planned-module-card"]')).toHaveLength(3)
    expect(wrapper.text()).toContain('AI 客服')
    expect(wrapper.text()).toContain('我的案例')
    expect(wrapper.text()).toContain('问题反馈')
    expect(wrapper.text()).toContain('AI 帮助次数')
    expect(wrapper.text()).toContain('待启用')
    expect(wrapper.text()).toContain('售后助手')
    expect(wrapper.text()).toContain('规划中')
    expect(wrapper.get('[data-testid="enter-ai-chat"]').attributes('href')).toBe('/ai-chat')
  })
})
