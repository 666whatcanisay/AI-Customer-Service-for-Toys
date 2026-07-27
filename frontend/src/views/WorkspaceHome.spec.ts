import { mount } from '@vue/test-utils'
import { ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import {
  clearCustomerSessionActivity,
  recordAiAssist,
  recordAiFeedbackSubmission
} from '@/workspace/customerSessionActivity'
import {
  clearExperienceCaseSubmissions,
  recordExperienceCaseSubmission
} from '@/workspace/experienceCaseSession'
import { SystemStatusKey } from '@/workspace/systemStatus'
import { TesterIdentityKey } from '@/workspace/testerIdentity'
import WorkspaceHome from './WorkspaceHome.vue'

describe('WorkspaceHome', () => {
  afterEach(() => {
    clearCustomerSessionActivity()
    clearExperienceCaseSubmissions()
  })

  it('shows the daily AI entry, real-workflow links and clearly planned modules', () => {
    recordAiAssist()
    recordAiAssist()
    recordAiFeedbackSubmission()
    recordExperienceCaseSubmission({
      storeCode: 'PDD-SM',
      productId: 'PROD-001',
      skuId: 'SKU-RED',
      caseId: 'CEC-001',
      feedbackType: 'ADOPTED',
      createdBy: 'TESTER-ONE',
      reviewStatus: 'NEW',
      submittedAt: '2026-07-27 12:00:00'
    })
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
    expect(wrapper.text()).toContain('今日 AI 辅助')
    expect(wrapper.text()).toContain('本次会话')
    expect(wrapper.get('[data-testid="today-ai-assist-count"]').text()).toBe('2')
    expect(wrapper.get('[data-testid="experience-case-count"]').text()).toBe('1')
    expect(wrapper.get('[data-testid="feedback-count"]').text()).toBe('1')
    expect(wrapper.get('[data-testid="home-readiness"]').text()).toContain('AI 可用，商品资料正在连接')
    expect(wrapper.get('[data-testid="home-readiness"]').text()).toContain('查看商品状态')
    expect(wrapper.get('[data-testid="start-checklist"]').text()).toContain('完成一条咨询，只需三步')
    expect(wrapper.get('[data-testid="start-checklist"]').text()).toContain('确认商品上下文')
    expect(wrapper.get('[data-testid="start-checklist"]').text()).toContain('复制并沉淀结果')
    expect(wrapper.get('[data-testid="work-rhythm-guide"]').text()).toContain('第一次使用')
    expect(wrapper.get('[data-testid="work-rhythm-guide"]').text()).toContain('高频使用')
    expect(wrapper.get('[data-testid="work-rhythm-guide"]').text()).toContain('处理下一条咨询')
    expect(wrapper.text()).toContain('售后助手')
    expect(wrapper.text()).toContain('规划中')
    expect(wrapper.get('[data-testid="enter-ai-chat"]').attributes('href')).toBe('/ai-chat')
  })
})
