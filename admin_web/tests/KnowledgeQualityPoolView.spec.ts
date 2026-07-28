import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import KnowledgeQualityPoolView from '../src/views/KnowledgeQualityPoolView.vue'
import { listKnowledgeQualityAssessments } from '../src/api/client'

vi.mock('../src/api/client', () => ({
  apiErrorMessage: vi.fn(() => '资料质量服务暂时不可用'),
  listKnowledgeQualityAssessments: vi.fn(),
}))

const mockedList = vi.mocked(listKnowledgeQualityAssessments)

describe('KnowledgeQualityPoolView', () => {
  beforeEach(() => mockedList.mockReset())

  it('shows an operator-facing repair recommendation and retains technical details below it', async () => {
    mockedList.mockResolvedValue({
      total: 1,
      items: [{
        assessment_id: 'KQA-TEST-1', material_id: 'KMT-TEST-1', revision: 1, content_hash: 'sha256:test',
        analysis_run_id: 'KQA-RUN-1', model_version: 'qwen3.5:9b', prompt_version: 'knowledge-quality-v1',
        overall_status: 'ANALYZED', summary: '包装来源还需要运营核对。', created_at: '2026-07-28T00:00:00Z',
        gaps: [{ gap_id: 'KQG-TEST-1', gap_code: 'PACKAGING_SOURCE', severity: 'MEDIUM', title: '包装来源待核对', description: '资料中没有来源版本。', recommended_action: '核对后上传修正版本。', status: 'OPEN' }],
      }],
    })
    const wrapper = mount(KnowledgeQualityPoolView)
    await flushPromises()
    expect(wrapper.text()).toContain('资料质量与补充')
    expect(wrapper.text()).toContain('包装来源还需要运营核对。')
    await wrapper.get('.link-button').trigger('click')
    expect(wrapper.text()).toContain('核对后上传修正版本。')
    expect(wrapper.text()).not.toContain('发布知识')
  })
})
