import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import { createMemoryHistory, createRouter, RouterView } from 'vue-router'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import KnowledgeEditorView from '../src/views/KnowledgeEditorView.vue'

const apiMocks = vi.hoisted(() => ({
  apiErrorMessage: vi.fn(() => '暂时不可用'),
  getKnowledgeMaterialDiff: vi.fn(),
  getKnowledgeMaterialRevision: vi.fn(),
  getProductKnowledgeOverview: vi.fn(),
  getProductKnowledgeProduct: vi.fn(),
  getReplyReadinessQuestionSet: vi.fn(),
  listKnowledgeMaterialRevisions: vi.fn(),
  listProductKnowledgeProducts: vi.fn(),
  uploadKnowledgeMaterial: vi.fn(),
}))

vi.mock('../src/api/client', () => apiMocks)

const tech = { store_code: 'STORE-ONE', platform: 'pinduoduo', product_id: 'PRODUCT-ONE', product_code: null, sku_id: null, sku_code: null, source_id: null, material_id: null, revision: null, content_hash: null }

function materialDetail(templateType: string, editableRecord: Record<string, string>) {
  return {
    material_id: 'KMT-1', revision: 2, store_code: 'STORE-ONE', product_id: 'PRODUCT-ONE', sku_id: templateType === 'SKU_DIFFERENCE' ? 'SKU-ONE' : null,
    display_name: '合成知识资料', material_status: 'RECOGNIZED', submitted_by: '历史提交人', updated_at: '2026-08-14T00:00:00Z',
    recognition_summary: { template_type: templateType }, editable_record: editableRecord,
  }
}

function controlForLabel(wrapper: VueWrapper, text: string) {
  const label = wrapper.findAll('label').find((item) => item.text().trim().startsWith(text))
  if (!label) throw new Error(`missing label: ${text}`)
  return label.find('input,textarea,select')
}

async function mountEditor(path = '/knowledge-editor?store=STORE-ONE&product=PRODUCT-ONE') {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [
      { path: '/knowledge-editor', component: KnowledgeEditorView },
      { path: '/reply-readiness', component: { template: '<div>风险池</div>' } },
      { path: '/knowledge-review', component: { template: '<div>审核队列</div>' } },
      { path: '/other', component: { template: '<div>其他页面</div>' } },
    ],
  })
  await router.push(path)
  await router.isReady()
  const wrapper = mount(RouterView, { global: { plugins: [router] } })
  await flushPromises()
  return { wrapper, router }
}

describe('KnowledgeEditorView', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    apiMocks.getProductKnowledgeOverview.mockResolvedValue({
      stores: [{ store_name: '木木小栈拼多多旗舰店', technical_details: tech }],
    })
    apiMocks.listProductKnowledgeProducts.mockResolvedValue({
      items: [{ product_name: 'Q66消防局积木', technical_details: tech }], total: 1,
    })
    apiMocks.getProductKnowledgeProduct.mockResolvedValue({
      skus: [{ sku_name: '豪华版', technical_details: { ...tech, product_id: null, sku_id: 'SKU-ONE' } }],
    })
    apiMocks.getReplyReadinessQuestionSet.mockResolvedValue({
      schema_version: 'pdd-reply-readiness-question-set.v1', baseline_version: 'pdd-common-questions.v1', fingerprint: 'a'.repeat(64),
      questions: [
        { question_id: 'PDD-PACKAGING', canonical_question: '是什么包装' },
        { question_id: 'PDD-INSTALLATION', canonical_question: '怎么安装' },
      ],
    })
    apiMocks.uploadKnowledgeMaterial.mockResolvedValue({
      material_id: 'KMT-1', revision: 1, content_hash: 'sha256:test', material_status: 'RECOGNIZED',
      recognition_summary: { detected_fields: ['商品简介', '资料来源'] },
    })
    apiMocks.listKnowledgeMaterialRevisions.mockResolvedValue({
      material_id: 'KMT-1', total: 1,
      items: [{ material_id: 'KMT-1', revision: 2, material_status: 'RECOGNIZED', submitted_by: '历史提交人' }],
    })
    apiMocks.getKnowledgeMaterialDiff.mockResolvedValue({ changes: [] })
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('submits Chinese product knowledge without asking the operator for technical fields', async () => {
    const { wrapper } = await mountEditor()
    expect(wrapper.text()).toContain('手工补充知识')
    expect(wrapper.text()).toContain('SKU差异知识')
    expect(wrapper.text()).not.toContain('product_id')
    expect(wrapper.text()).not.toContain('tenant_id')

    await controlForLabel(wrapper, '商品简介').setValue('消防主题机械积木。')
    await controlForLabel(wrapper, '来源日期').setValue('2026-07-20')
    await controlForLabel(wrapper, '资料来源').setValue('商品说明书第2页')
    await controlForLabel(wrapper, '本次提交人').setValue('运营测试')
    await wrapper.get('form').trigger('submit')
    await flushPromises()

    expect(apiMocks.uploadKnowledgeMaterial).toHaveBeenCalledWith(expect.any(File), expect.objectContaining({ template_type: 'PRODUCT_KNOWLEDGE', material_type: 'PRODUCT_SPEC' }))
    expect(wrapper.text()).toContain('已保存为待审核资料 v1')
    expect(wrapper.text()).toContain('旧版本没有被覆盖')
    expect(wrapper.findAll('a').some((item) => item.attributes('href')?.includes('material_revision=1'))).toBe(true)
  })

  it.each([
    ['PRODUCT_KNOWLEDGE', { 商品简介: '历史商品简介', 图片一致性说明: '同款实拍', 快递选择策略: '仓库安排', 隐私包装: '无商品名外箱', 品牌授权证据: '授权书SYNTHETIC-1', 资料来源: '说明书', 来源日期: '2026-08-01', 是否人工确认: '是' }, '商品简介', '历史商品简介'],
    ['SKU_DIFFERENCE', { 颜色款式: '红色消防款', 规格区别: '含灯光', 包装区别: '彩盒', 数量区别: '1200颗', 尺寸区别: '40cm', 玩法区别: '遥控', SKU常见问题: '是否含灯', SKU安全提醒: '成人陪同', 资料来源: '包装', 来源日期: '2026-08-02', 确认状态: '已确认' }, '颜色款式', '红色消防款'],
    ['FAQ', { 关联问题ID: 'PDD-PACKAGING', 客户常问问题: '有灯吗', 标准回答: '该SKU含灯光组件。', 适用场景: '售前', 风险等级: '低', 是否需要人工确认: '否', 资料来源: '说明书', 来源日期: '2026-08-03', 事实确认状态: '已确认' }, '标准回答', '该SKU含灯光组件。'],
    ['SAFETY_RULE', { 关联问题ID: 'PDD-INSTALLATION', 适用年龄: '6岁以上', 安全主题: '小零件', 风险等级: '中', 安全提醒: '建议成人陪同', 禁止承诺内容: '不得忽略年龄限制', 需要人工确认情况: '年龄不清楚', 必须转人工情况: '客户要求低龄使用', 资料来源: '警示标签', 来源日期: '2026-08-04', 事实确认状态: '待确认' }, '安全主题', '小零件'],
  ])('fully rehydrates %s while locking immutable identity', async (templateType, record, label, expected) => {
    apiMocks.getKnowledgeMaterialRevision.mockResolvedValue(materialDetail(templateType, record))
    const { wrapper } = await mountEditor('/knowledge-editor?material_id=KMT-1&material_revision=2')

    expect(wrapper.text()).toContain('创建知识新修订')
    expect(controlForLabel(wrapper, label).element).toHaveProperty('value', expected)
    expect(controlForLabel(wrapper, '本次提交人').element).toHaveProperty('value', '')
    if (templateType === 'PRODUCT_KNOWLEDGE') {
      expect(controlForLabel(wrapper, '图片一致性说明').element).toHaveProperty('value', '同款实拍')
      expect(controlForLabel(wrapper, '品牌授权证据').element).toHaveProperty('value', '授权书SYNTHETIC-1')
    }
    if (templateType === 'FAQ' || templateType === 'SAFETY_RULE') {
      expect(controlForLabel(wrapper, '关联基线问题').element).toHaveProperty('value', (record as Record<string, string>)['关联问题ID'])
    }
    const identitySelects = wrapper.findAll('.editor-card')[0].findAll('select')
    expect(identitySelects).toHaveLength(3)
    expect(identitySelects.every((item) => item.attributes('disabled') !== undefined)).toBe(true)
    expect(wrapper.findAll('input[type="radio"]').every((item) => item.attributes('disabled') !== undefined)).toBe(true)
  })

  it('warns about conflicting, estimated and prohibited answer facts without blocking draft editing', async () => {
    const { wrapper } = await mountEditor()
    await controlForLabel(wrapper, '颗粒数量').setValue('估测1000颗左右')
    await controlForLabel(wrapper, '成品尺寸').setValue('资料同时写了30cm和40cm')
    await controlForLabel(wrapper, '推荐回答方向').setValue('全部正品，24小时必到')

    expect(wrapper.text()).toContain('尺寸信息冲突')
    expect(wrapper.text()).toContain('颗粒数不是确定事实')
    expect(wrapper.text()).toContain('真伪承诺缺少授权边界')
    expect(wrapper.text()).toContain('固定时效承诺')
    expect(wrapper.text()).toContain('可以继续保存为待审核草稿')
  })

  it('blocks route changes when the operator rejects discarding unsaved edits', async () => {
    const confirm = vi.spyOn(globalThis, 'confirm').mockReturnValue(false)
    const { wrapper, router } = await mountEditor()
    await controlForLabel(wrapper, '商品简介').setValue('尚未保存的内容')

    await router.push('/other')
    await flushPromises()

    expect(confirm).toHaveBeenCalled()
    expect(router.currentRoute.value.path).toBe('/knowledge-editor')
    expect(controlForLabel(wrapper, '商品简介').element).toHaveProperty('value', '尚未保存的内容')
  })

  it('opens the requested FAQ question from a readiness deep link', async () => {
    const { wrapper } = await mountEditor('/knowledge-editor?store=STORE-ONE&product=PRODUCT-ONE&question_id=PDD-PACKAGING&template=FAQ&fact_key=package_contents')

    expect(wrapper.text()).toContain('正在补充“是什么包装”')
    expect(wrapper.text()).toContain('首要缺口：package_contents')
    expect(controlForLabel(wrapper, '关联基线问题').element).toHaveProperty('value', 'PDD-PACKAGING')
    expect(wrapper.find('input[type="radio"][value="FAQ"]').attributes('checked')).toBeDefined()
  })
})
