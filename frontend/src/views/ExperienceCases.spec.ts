import { mount } from '@vue/test-utils'
import ElementPlus from 'element-plus'
import { ref } from 'vue'
import { afterEach, describe, expect, it } from 'vitest'
import { clearExperienceCaseSubmissions, recordExperienceCaseSubmission } from '@/workspace/experienceCaseSession'
import { TesterIdentityKey } from '@/workspace/testerIdentity'
import ExperienceCases from './ExperienceCases.vue'

const mountPage = () => mount(ExperienceCases, {
  global: {
    plugins: [ElementPlus],
    provide: { [TesterIdentityKey as symbol]: { identity: ref({ reporterId: 'TESTER-ONE', reporterName: '小木', defaultStoreCode: 'PDD-SM' }) } },
    stubs: { RouterLink: { props: ['to'], template: '<a :href="String(to)"><slot /></a>' } }
  }
})

describe('ExperienceCases', () => {
  afterEach(clearExperienceCaseSubmissions)

  it('shows only a successful session summary and its Chinese status', () => {
    recordExperienceCaseSubmission({ caseId: 'CEC-001', storeCode: 'PDD-SM', productId: 'PROD-1', skuId: 'SKU-1', feedbackType: 'EDITED_ADOPTED', createdBy: 'TESTER-ONE', reviewStatus: 'REVIEWING', submittedAt: '2026-07-25 12:00' })
    const wrapper = mountPage()
    expect(wrapper.get('[data-testid="experience-case-list"]').text()).toContain('审核中')
    expect(wrapper.text()).toContain('修改后采用')
    expect(wrapper.get('[data-testid="experience-case-list"]').text()).not.toContain('AI 回复')
    expect(wrapper.get('[data-testid="experience-case-journey"]').text()).toContain('等待人工审核')
    expect(wrapper.get('[data-testid="experience-case-list"] .status-reviewing').text()).toContain('审核中')
  })

  it('does not invent a remote list when no real submission exists', () => {
    expect(mountPage().get('[data-testid="experience-case-empty"]').text()).toContain('还没有成功提交')
  })
})
