<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { onBeforeRouteLeave, RouterLink, useRoute } from 'vue-router'

import {
  apiErrorMessage,
  getKnowledgeMaterialDiff,
  getKnowledgeMaterialRevision,
  getProductKnowledgeOverview,
  getProductKnowledgeProduct,
  getReplyReadinessQuestionSet,
  listKnowledgeMaterialRevisions,
  listProductKnowledgeProducts,
  uploadKnowledgeMaterial,
  type KnowledgeMaterial,
  type KnowledgeMaterialDiff,
  type KnowledgeMaterialType,
  type KnowledgeTemplateType,
  type ProductKnowledgeDetail,
  type ProductKnowledgeListItem,
  type ReplyReadinessQuestionSet,
  type StoreKnowledgeSummary,
} from '../api/client'
import { displayStatus } from '../presentation'

type EditableTemplate = 'PRODUCT_KNOWLEDGE' | 'SKU_DIFFERENCE' | 'FAQ' | 'SAFETY_RULE'
type FormKey = keyof typeof form
type WarningItem = { code: string; title: string; message: string }

const route = useRoute()
const stores = ref<StoreKnowledgeSummary[]>([])
const products = ref<ProductKnowledgeListItem[]>([])
const productDetail = ref<ProductKnowledgeDetail | null>(null)
const loading = ref(true)
const productLoading = ref(false)
const revisionLoading = ref(false)
const submitting = ref(false)
const error = ref('')
const receipt = ref('')
const routeNotice = ref('')
const editingMaterialId = ref('')
const editingDisplayName = ref('')
const history = ref<KnowledgeMaterial[]>([])
const selectedHistoryRevision = ref<number | null>(null)
const diff = ref<KnowledgeMaterialDiff | null>(null)
const questionSet = ref<ReplyReadinessQuestionSet | null>(null)
const baselineSnapshot = ref('')
const deepLinkQuestionId = ref('')
const deepLinkFactKey = ref('')

let productLoadEpoch = 0
let revisionLoadEpoch = 0

const scope = reactive({ store_code: '', product_id: '', sku_id: '' })
const governance = reactive({ source: '', source_date: '', submitted_by: '', confirmed: '是' })
const form = reactive({
  template_type: 'PRODUCT_KNOWLEDGE' as EditableTemplate,
  product_summary: '', selling_points: '', age: '', material: '', safety: '', package_contents: '', usage: '', play: '',
  particle_count: '', finished_size: '', product_scale: '', weight: '', compatibility: '', installation: '',
  included_items: '', ship_origin: '', version_difference: '', image_status: '', video_status: '',
  image_match_policy: '', courier_policy: '', stealth_packaging: '', authenticity_evidence: '',
  prohibited_promises: '', realtime_lookup: '', manual_handling: '',
  color_style: '已确认无差异', specification_difference: '已确认无差异', package_difference: '已确认无差异',
  quantity_difference: '已确认无差异', size_difference: '已确认无差异', play_difference: '已确认无差异', sku_faq: '', sku_safety: '',
  question: '', answer: '', scenario: '', risk_level: '中', manual_confirmation: '否',
  related_question_id: '',
  safety_topic: '', forbidden_claim: '', confirmation_condition: '', handoff_condition: '',
})

const templateOptions: Array<{ value: EditableTemplate; description: string }> = [
  { value: 'PRODUCT_KNOWLEDGE', description: '补充商品参数、包装、图片资料和回答限制' },
  { value: 'SKU_DIFFERENCE', description: '记录具体SKU与其他款式的已确认差异' },
  { value: 'FAQ', description: '维护有来源依据的客户问题和标准回答' },
  { value: 'SAFETY_RULE', description: '维护安全提醒、禁止承诺和转人工条件' },
]

const scopedProducts = computed(() => products.value.filter((item) => item.technical_details.store_code === scope.store_code))
const selectedStore = computed(() => stores.value.find((item) => item.technical_details.store_code === scope.store_code))
const selectedProduct = computed(() => scopedProducts.value.find((item) => item.technical_details.product_id === scope.product_id))
const selectedSku = computed(() => productDetail.value?.skus.find((item) => item.technical_details.sku_id === scope.sku_id))
const skuRequired = computed(() => form.template_type === 'SKU_DIFFERENCE')
const revisionMode = computed(() => Boolean(editingMaterialId.value))
const latestRevision = computed(() => history.value[0] || null)
const linkedQuestion = computed(() => questionSet.value?.questions.find((item) => item.question_id === deepLinkQuestionId.value) || null)
const editHint = computed(() => {
  if (!linkedQuestion.value) return ''
  const suffix = deepLinkFactKey.value ? `，首要缺口：${deepLinkFactKey.value}` : ''
  return `正在补充“${linkedQuestion.value.canonical_question}”${suffix}。保存新修订后返回风险池复跑。`
})

function defaultForm(templateType: EditableTemplate = 'PRODUCT_KNOWLEDGE') {
  return {
    template_type: templateType,
    product_summary: '', selling_points: '', age: '', material: '', safety: '', package_contents: '', usage: '', play: '',
    particle_count: '', finished_size: '', product_scale: '', weight: '', compatibility: '', installation: '',
    included_items: '', ship_origin: '', version_difference: '', image_status: '', video_status: '',
    image_match_policy: '', courier_policy: '', stealth_packaging: '', authenticity_evidence: '',
    prohibited_promises: '', realtime_lookup: '', manual_handling: '',
    color_style: '已确认无差异', specification_difference: '已确认无差异', package_difference: '已确认无差异',
    quantity_difference: '已确认无差异', size_difference: '已确认无差异', play_difference: '已确认无差异', sku_faq: '', sku_safety: '',
    question: '', answer: '', scenario: '', risk_level: '中', manual_confirmation: '否', related_question_id: '',
    safety_topic: '', forbidden_claim: '', confirmation_condition: '', handoff_condition: '',
  }
}

function currentSnapshot(): string {
  return JSON.stringify({ form: { ...form }, governance: { ...governance } })
}

const dirty = computed(() => Boolean(baselineSnapshot.value) && currentSnapshot() !== baselineSnapshot.value)

function markClean(): void {
  baselineSnapshot.value = currentSnapshot()
}

function confirmDiscard(): boolean {
  return !dirty.value || globalThis.confirm('当前有未保存的修改。离开后这些内容会丢失，确定继续吗？')
}

function resetEditor(templateType: EditableTemplate = 'PRODUCT_KNOWLEDGE'): void {
  Object.assign(form, defaultForm(templateType))
  Object.assign(governance, { source: '', source_date: '', submitted_by: '', confirmed: '是' })
  error.value = ''
  receipt.value = ''
  markClean()
}

function materialType(templateType: KnowledgeTemplateType): KnowledgeMaterialType {
  if (templateType === 'FAQ') return 'FAQ_SOURCE'
  if (templateType === 'SAFETY_RULE') return 'SAFETY_INSTRUCTION'
  return 'PRODUCT_SPEC'
}

function buildRow(): Record<string, string> {
  const common = {
    店铺名称: selectedStore.value?.store_name || '',
    商品名称: selectedProduct.value?.product_name || '',
  }
  if (form.template_type === 'PRODUCT_KNOWLEDGE') {
    return {
      ...common, 商品简介: form.product_summary, 核心卖点: form.selling_points, 适用年龄: form.age,
      材质信息: form.material, 安全提醒: form.safety, 包装内容: form.package_contents, 使用说明: form.usage,
      颗粒数量: form.particle_count, 成品尺寸: form.finished_size, 商品比例: form.product_scale,
      商品重量: form.weight, 兼容性: form.compatibility, 安装方式: form.installation,
      随附物品: form.included_items, 发货地: form.ship_origin, 版本差异: form.version_difference,
      图片资料状态: form.image_status, 视频资料状态: form.video_status, 禁止承诺: form.prohibited_promises,
      图片一致性说明: form.image_match_policy, 快递选择策略: form.courier_policy,
      隐私包装: form.stealth_packaging, 品牌授权证据: form.authenticity_evidence,
      实时查询要求: form.realtime_lookup, 人工处理条件: form.manual_handling,
      玩法介绍: form.play, 客户常问问题: form.question, 推荐回答方向: form.answer,
      资料来源: governance.source, 来源日期: governance.source_date, 是否人工确认: governance.confirmed, 备注: '',
    }
  }
  if (form.template_type === 'SKU_DIFFERENCE') {
    return {
      ...common, SKU名称: selectedSku.value?.sku_name || '', 颜色款式: form.color_style,
      规格区别: form.specification_difference, 包装区别: form.package_difference, 数量区别: form.quantity_difference,
      尺寸区别: form.size_difference, 玩法区别: form.play_difference, SKU常见问题: form.sku_faq,
      SKU安全提醒: form.sku_safety, 资料来源: governance.source, 来源日期: governance.source_date,
      确认状态: governance.confirmed === '是' ? '已确认' : '待确认', 备注: '',
    }
  }
  if (form.template_type === 'FAQ') {
    return {
      ...common, SKU名称: selectedSku.value?.sku_name || '全部SKU', 关联问题ID: form.related_question_id, 客户常问问题: form.question,
      标准回答: form.answer, 适用场景: form.scenario, 是否需要人工确认: form.manual_confirmation,
      风险等级: form.risk_level, 资料来源: governance.source, 来源日期: governance.source_date,
      事实确认状态: governance.confirmed === '是' ? '已确认' : '待确认', 备注: '',
    }
  }
  return {
    ...common, 关联问题ID: form.related_question_id, 适用年龄: form.age, 安全主题: form.safety_topic, 风险等级: form.risk_level,
    安全提醒: form.safety, 禁止承诺内容: form.forbidden_claim, 需要人工确认情况: form.confirmation_condition,
    必须转人工情况: form.handoff_condition, 资料来源: governance.source, 来源日期: governance.source_date,
    事实确认状态: governance.confirmed === '是' ? '已确认' : '待确认', 备注: '',
  }
}

function valueFor(record: Record<string, string>, ...labels: string[]): string {
  for (const label of labels) if (record[label] !== undefined) return record[label]
  return ''
}

function applyEditableRecord(record: Record<string, string>, templateType: EditableTemplate): void {
  Object.assign(form, defaultForm(templateType))
  if (templateType === 'SKU_DIFFERENCE') {
    Object.assign(form, {
      color_style: '', specification_difference: '', package_difference: '',
      quantity_difference: '', size_difference: '', play_difference: '',
    })
  }
  const commonFields: Array<[FormKey, string]> = [
    ['product_summary', '商品简介'], ['selling_points', '核心卖点'], ['age', '适用年龄'],
    ['material', '材质信息'], ['safety', '安全提醒'], ['package_contents', '包装内容'],
    ['usage', '使用说明'], ['play', '玩法介绍'], ['particle_count', '颗粒数量'],
    ['finished_size', '成品尺寸'], ['product_scale', '商品比例'], ['weight', '商品重量'],
    ['compatibility', '兼容性'], ['installation', '安装方式'], ['included_items', '随附物品'],
    ['ship_origin', '发货地'], ['version_difference', '版本差异'], ['image_status', '图片资料状态'],
    ['video_status', '视频资料状态'], ['prohibited_promises', '禁止承诺'],
    ['image_match_policy', '图片一致性说明'], ['courier_policy', '快递选择策略'],
    ['stealth_packaging', '隐私包装'], ['authenticity_evidence', '品牌授权证据'],
    ['realtime_lookup', '实时查询要求'], ['manual_handling', '人工处理条件'],
  ]
  const templateFields: Record<EditableTemplate, Array<[FormKey, string]>> = {
    PRODUCT_KNOWLEDGE: [['question', '客户常问问题'], ['answer', '推荐回答方向']],
    SKU_DIFFERENCE: [
      ['color_style', '颜色款式'], ['specification_difference', '规格区别'],
      ['package_difference', '包装区别'], ['quantity_difference', '数量区别'],
      ['size_difference', '尺寸区别'], ['play_difference', '玩法区别'],
      ['sku_faq', 'SKU常见问题'], ['sku_safety', 'SKU安全提醒'],
    ],
    FAQ: [
      ['related_question_id', '关联问题ID'], ['question', '客户常问问题'], ['answer', '标准回答'], ['scenario', '适用场景'],
      ['risk_level', '风险等级'], ['manual_confirmation', '是否需要人工确认'],
    ],
    SAFETY_RULE: [
      ['related_question_id', '关联问题ID'], ['age', '适用年龄'], ['safety_topic', '安全主题'], ['risk_level', '风险等级'],
      ['safety', '安全提醒'], ['forbidden_claim', '禁止承诺内容'],
      ['confirmation_condition', '需要人工确认情况'], ['handoff_condition', '必须转人工情况'],
    ],
  }
  const fields = templateType === 'PRODUCT_KNOWLEDGE'
    ? [...commonFields, ...templateFields.PRODUCT_KNOWLEDGE]
    : templateFields[templateType]
  for (const [field, label] of fields) {
    if (record[label] !== undefined) form[field] = record[label] as never
  }
  governance.source = valueFor(record, '资料来源')
  governance.source_date = valueFor(record, '来源日期')
  const confirmation = valueFor(record, '是否人工确认', '确认状态', '事实确认状态')
  governance.confirmed = confirmation && !['否', '待确认', '未确认'].includes(confirmation) ? '是' : '否'
  governance.submitted_by = ''
}

const safetyWarnings = computed<WarningItem[]>(() => {
  const warnings: WarningItem[] = []
  const allText = Object.values(form).join(' ')
  if (/30\s*(cm|厘米)/i.test(allText) && /40\s*(cm|厘米)/i.test(allText)) {
    warnings.push({ code: 'SIZE_CONFLICT', title: '尺寸信息冲突', message: '同一范围同时出现约30cm和约40cm，回答评测会保持高风险。' })
  }
  if (/(估测|估计|大概|可能|左右|约)/.test(form.particle_count)) {
    warnings.push({ code: 'ESTIMATED_PARTICLES', title: '颗粒数不是确定事实', message: '估测颗粒数不能作为确定回答依据，请补充已确认来源。' })
  }
  if (/(全部正品|保证正品|百分百正品|均为正品)/.test(allText)) {
    warnings.push({ code: 'AUTHENTICITY_PROMISE', title: '真伪承诺缺少授权边界', message: '没有品牌授权证据时不得承诺“全部正品”。' })
  }
  if (/(24|48|72)\s*(小时|h).{0,8}(必到|送达|发货|到货)/i.test(allText)) {
    warnings.push({ code: 'FIXED_SLA', title: '固定时效承诺', message: '固定24/48/72小时发货或送达承诺不能通过回答安全门。' })
  }
  return warnings
})

const requiredFields = computed(() => {
  const common = [
    { label: '店铺', value: scope.store_code }, { label: '商品', value: scope.product_id },
    { label: '资料来源', value: governance.source }, { label: '来源日期', value: governance.source_date },
    { label: '提交人', value: governance.submitted_by },
  ]
  if (form.template_type === 'PRODUCT_KNOWLEDGE') return [...common, { label: '商品简介', value: form.product_summary }]
  if (form.template_type === 'SKU_DIFFERENCE') return [
    ...common, { label: 'SKU', value: scope.sku_id }, { label: '颜色款式', value: form.color_style },
    { label: '规格区别', value: form.specification_difference }, { label: '包装区别', value: form.package_difference },
    { label: '数量区别', value: form.quantity_difference }, { label: '尺寸区别', value: form.size_difference },
    { label: '玩法区别', value: form.play_difference },
  ]
  if (form.template_type === 'FAQ') return [
    ...common, { label: '关联问题', value: form.related_question_id }, { label: '客户问题', value: form.question }, { label: '标准回答', value: form.answer },
    { label: '适用场景', value: form.scenario },
  ]
  return [
    ...common, { label: '关联问题', value: form.related_question_id }, { label: '安全主题', value: form.safety_topic }, { label: '安全提醒', value: form.safety },
    { label: '禁止承诺', value: form.forbidden_claim }, { label: '必须转人工情况', value: form.handoff_condition },
  ]
})
const missingRequired = computed(() => requiredFields.value.filter((item) => !String(item.value || '').trim()).map((item) => item.label))
const completionPercent = computed(() => Math.round(((requiredFields.value.length - missingRequired.value.length) / requiredFields.value.length) * 100))

async function loadProductDetail(): Promise<void> {
  const epoch = ++productLoadEpoch
  productLoading.value = true
  try {
    const productId = scope.product_id
    const [detail, questions] = productId
      ? await Promise.all([
          getProductKnowledgeProduct(productId),
          getReplyReadinessQuestionSet({ store_code: scope.store_code, product_id: productId }),
        ])
      : [null, null]
    if (epoch !== productLoadEpoch || productId !== scope.product_id) return
    productDetail.value = detail
    questionSet.value = questions
    if (!detail?.skus.some((item) => item.technical_details.sku_id === scope.sku_id)) scope.sku_id = ''
  } finally {
    if (epoch === productLoadEpoch) productLoading.value = false
  }
}

async function selectStore(event: Event): Promise<void> {
  const value = (event.target as HTMLSelectElement).value
  if (!confirmDiscard()) {
    ;(event.target as HTMLSelectElement).value = scope.store_code
    return
  }
  productLoadEpoch += 1
  scope.store_code = value
  scope.product_id = ''
  scope.sku_id = ''
  productDetail.value = null
  questionSet.value = null
  editingMaterialId.value = ''
  editingDisplayName.value = ''
  history.value = []
  selectedHistoryRevision.value = null
  diff.value = null
  resetEditor()
}

async function selectProduct(event: Event): Promise<void> {
  const value = (event.target as HTMLSelectElement).value
  if (!confirmDiscard()) {
    ;(event.target as HTMLSelectElement).value = scope.product_id
    return
  }
  scope.product_id = value
  scope.sku_id = ''
  resetEditor(form.template_type)
  try {
    await loadProductDetail()
  } catch (reason: unknown) {
    error.value = apiErrorMessage(reason)
  }
}

function selectSku(event: Event): void {
  const value = (event.target as HTMLSelectElement).value
  if (!confirmDiscard()) {
    ;(event.target as HTMLSelectElement).value = scope.sku_id
    return
  }
  scope.sku_id = value
  resetEditor(form.template_type)
}

function selectTemplate(value: EditableTemplate): void {
  if (revisionMode.value || value === form.template_type) return
  if (!confirmDiscard()) return
  resetEditor(value)
}

async function submit(): Promise<void> {
  if (submitting.value || missingRequired.value.length > 0 || !selectedStore.value || !selectedProduct.value || (skuRequired.value && !selectedSku.value)) return
  submitting.value = true
  error.value = ''
  receipt.value = ''
  try {
    const row = buildRow()
    const file = new File([JSON.stringify(row)], `${displayStatus(form.template_type)}补充.json`, { type: 'application/json' })
    const result = await uploadKnowledgeMaterial(file, {
      store_code: scope.store_code,
      product_id: scope.product_id,
      sku_id: scope.sku_id || undefined,
      material_type: materialType(form.template_type),
      template_type: form.template_type,
      display_name: editingDisplayName.value || `${selectedProduct.value.product_name} · ${displayStatus(form.template_type)}补充`,
      submitted_by: governance.submitted_by,
      material_id: editingMaterialId.value || undefined,
    })
    editingMaterialId.value = result.material_id
    if (!editingDisplayName.value) editingDisplayName.value = `${selectedProduct.value.product_name} · ${displayStatus(form.template_type)}补充`
    selectedHistoryRevision.value = result.revision
    receipt.value = `已保存为待审核资料 v${result.revision}，识别到 ${result.recognition_summary.detected_fields.length} 项知识字段。旧版本没有被覆盖。`
    try {
      history.value = (await listKnowledgeMaterialRevisions(result.material_id)).items
    } catch {
      // The immutable revision was saved successfully; history can be refreshed later.
    }
    markClean()
  } catch (reason: unknown) {
    error.value = apiErrorMessage(reason)
  } finally {
    submitting.value = false
  }
}

async function loadRevision(materialId: string, revision: number, force = false): Promise<void> {
  if (!force && !confirmDiscard()) return
  const epoch = ++revisionLoadEpoch
  revisionLoading.value = true
  error.value = ''
  receipt.value = ''
  try {
    const detail = await getKnowledgeMaterialRevision(materialId, revision)
    if (epoch !== revisionLoadEpoch) return
    editingMaterialId.value = materialId
    editingDisplayName.value = detail.display_name
    selectedHistoryRevision.value = revision
    scope.store_code = detail.store_code
    scope.product_id = detail.product_id
    scope.sku_id = detail.sku_id || ''
    const templateType = (detail.recognition_summary.template_type || 'PRODUCT_KNOWLEDGE') as EditableTemplate
    await loadProductDetail()
    if (epoch !== revisionLoadEpoch) return
    if (detail.editable_record) applyEditableRecord(detail.editable_record, templateType)
    else resetEditor(templateType)
    governance.submitted_by = ''
    history.value = (await listKnowledgeMaterialRevisions(materialId)).items
    if (epoch !== revisionLoadEpoch) return
    const latest = history.value[0]
    diff.value = latest && latest.revision !== revision
      ? await getKnowledgeMaterialDiff(materialId, revision, latest.revision)
      : null
    if (epoch === revisionLoadEpoch) markClean()
  } catch (reason: unknown) {
    if (epoch === revisionLoadEpoch) error.value = apiErrorMessage(reason)
  } finally {
    if (epoch === revisionLoadEpoch) revisionLoading.value = false
  }
}

function beforeUnload(event: BeforeUnloadEvent): void {
  if (!dirty.value) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteLeave(() => confirmDiscard())

onMounted(async () => {
  globalThis.addEventListener?.('beforeunload', beforeUnload)
  try {
    const [overview, productPage] = await Promise.all([getProductKnowledgeOverview(), listProductKnowledgeProducts()])
    stores.value = overview.stores
    products.value = productPage.items
    const requestedStore = typeof route.query.store === 'string' ? route.query.store : ''
    const requestedProduct = typeof route.query.product === 'string' ? route.query.product : ''
    const requestedSku = typeof route.query.sku === 'string' ? route.query.sku : ''
    const requestedMaterial = typeof route.query.material_id === 'string' ? route.query.material_id : ''
    const requestedRevision = Number(route.query.material_revision || route.query.revision || 0)
    const requestedQuestion = typeof route.query.question_id === 'string' ? route.query.question_id : ''
    const requestedFact = typeof route.query.fact_key === 'string' ? route.query.fact_key : ''
    const requestedTemplate = typeof route.query.template === 'string' ? route.query.template : ''
    deepLinkQuestionId.value = requestedQuestion
    deepLinkFactKey.value = requestedFact
    if (requestedStore && stores.value.some((item) => item.technical_details.store_code === requestedStore)) scope.store_code = requestedStore
    else if (requestedStore) routeNotice.value = '链接中的店铺不可用，请重新选择。'
    const productMatchesStore = products.value.some((item) => item.technical_details.product_id === requestedProduct
      && item.technical_details.store_code === scope.store_code)
    if (requestedProduct && productMatchesStore) {
      scope.product_id = requestedProduct
      await loadProductDetail()
      if (requestedSku && productDetail.value?.skus.some((item) => item.technical_details.sku_id === requestedSku)) scope.sku_id = requestedSku
      else if (requestedSku) routeNotice.value = '链接中的SKU不属于当前商品，已清除。'
    } else if (requestedProduct) routeNotice.value = '链接中的商品不属于当前店铺，请重新选择。'
    if (requestedMaterial && requestedRevision > 0) await loadRevision(requestedMaterial, requestedRevision, true)
    else if (templateOptions.some((item) => item.value === requestedTemplate)) resetEditor(requestedTemplate as EditableTemplate)
    if (requestedQuestion && ['FAQ', 'SAFETY_RULE'].includes(form.template_type) && !form.related_question_id) {
      form.related_question_id = requestedQuestion
    }
    if (!requestedMaterial && !requestedTemplate) markClean()
  } catch (reason: unknown) {
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
})

onBeforeUnmount(() => {
  productLoadEpoch += 1
  revisionLoadEpoch += 1
  globalThis.removeEventListener?.('beforeunload', beforeUnload)
})
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div><p class="eyebrow">商品知识补充</p><h1>{{ revisionMode ? '创建知识新修订' : '手工补充知识' }}</h1><p>只填写已核实事实；保存后进入人工审核，不会自动发布或发送。</p></div>
      <RouterLink class="button secondary" :to="{ path: '/knowledge-review', query: { store: scope.store_code, product: scope.product_id } }">查看审核队列</RouterLink>
    </div>

    <p v-if="routeNotice" class="notice" role="status">{{ routeNotice }}</p>
    <p v-if="editHint" class="notice" role="status">{{ editHint }}</p>
    <p v-if="loading" class="notice" role="status">正在读取店铺和商品…</p>
    <form v-else class="editor" @submit.prevent="submit">
      <section v-if="revisionMode" class="card revision-context">
        <div class="history-heading">
          <div>
            <p class="eyebrow">不可变修订</p>
            <h2>{{ editingDisplayName }}</h2>
            <p>当前以 v{{ selectedHistoryRevision }} 为基础创建新修订；店铺、商品、SKU、模板和资料身份已锁定，旧版本不会被覆盖。</p>
          </div>
          <RouterLink class="button secondary" :to="{ path: '/reply-readiness', query: { store: scope.store_code, product: scope.product_id, ...(scope.sku_id ? { sku: scope.sku_id } : {}), material_id: editingMaterialId, material_revision: selectedHistoryRevision } }">返回风险池</RouterLink>
        </div>
        <div class="revision-row" aria-label="知识历史版本">
          <button v-for="item in history" :key="item.revision" type="button" :class="{ active: item.revision === selectedHistoryRevision }" :disabled="revisionLoading" @click="loadRevision(item.material_id, item.revision)">
            v{{ item.revision }} · {{ item.material_status }} · {{ item.submitted_by }}
          </button>
        </div>
        <p v-if="revisionLoading" class="inline-status" role="status">正在读取所选历史版本…</p>
        <div v-if="diff" class="diff-panel">
          <div><strong>v{{ diff.from_revision }} 与最新 v{{ diff.to_revision }} 的变化</strong><button v-if="latestRevision" class="text-button" type="button" @click="loadRevision(latestRevision.material_id, latestRevision.revision)">返回最新版本</button></div>
          <p v-if="diff.changes.length === 0">没有字段变化。</p>
          <article v-for="item in diff.changes" :key="item.field"><strong>{{ item.field }}</strong><div><span>{{ item.before || '空' }}</span><b>→</b><span>{{ item.after || '空' }}</span></div></article>
        </div>
      </section>

      <section class="card editor-card">
        <div class="section-heading"><span class="step">1</span><div><h2>知识范围</h2><p>{{ revisionMode ? '修订模式下范围不可修改。' : '先选择店铺、商品和适用SKU。' }}</p></div></div>
        <div class="form-grid">
          <label>店铺<select :value="scope.store_code" required :disabled="revisionMode" @change="selectStore"><option value="">请选择店铺</option><option v-for="store in stores" :key="store.technical_details.store_code || store.store_name" :value="store.technical_details.store_code || ''">{{ store.store_name }}</option></select></label>
          <label>商品<select :value="scope.product_id" required :disabled="!scope.store_code || revisionMode || productLoading" @change="selectProduct"><option value="">请选择商品</option><option v-for="product in scopedProducts" :key="product.technical_details.product_id || product.product_name" :value="product.technical_details.product_id || ''">{{ product.product_name }}</option></select></label>
          <label>SKU{{ skuRequired ? '（必选）' : '（可选）' }}<select :value="scope.sku_id" :required="skuRequired" :disabled="!scope.product_id || revisionMode || productLoading" @change="selectSku"><option value="">适用于全部SKU</option><option v-for="sku in productDetail?.skus || []" :key="sku.technical_details.sku_id || sku.sku_name" :value="sku.technical_details.sku_id || ''">{{ sku.sku_name }}</option></select></label>
        </div>
        <p v-if="productLoading" class="inline-status" role="status">正在读取商品SKU…</p>
      </section>

      <section class="card editor-card">
        <div class="section-heading"><span class="step">2</span><div><h2>补充内容类型</h2><p>不同类型使用不同审核字段。</p></div></div>
        <div class="template-tabs" role="radiogroup" aria-label="知识模板类型">
          <label v-for="option in templateOptions" :key="option.value" :class="{ active: form.template_type === option.value, locked: revisionMode }">
            <input :checked="form.template_type === option.value" type="radio" name="template-type" :value="option.value" :disabled="revisionMode" @change="selectTemplate(option.value)">
            <strong>{{ displayStatus(option.value) }}</strong><span>{{ option.description }}</span>
          </label>
        </div>
      </section>

      <section class="card editor-card knowledge-section">
        <div class="section-heading"><span class="step">3</span><div><h2>填写已确认事实</h2><p>资料不足可以留空，不能用推测补齐。</p></div></div>

        <template v-if="form.template_type === 'PRODUCT_KNOWLEDGE'">
          <fieldset class="field-group"><legend>基础规格</legend><div class="form-grid"><label class="wide">商品简介<textarea v-model.trim="form.product_summary" required></textarea></label><label>核心卖点<textarea v-model.trim="form.selling_points"></textarea></label><label>适用年龄<input v-model.trim="form.age" placeholder="资料未提供时可留空"></label><label>材质信息<input v-model.trim="form.material"></label><label>颗粒数量<input v-model.trim="form.particle_count" placeholder="只填已确认值，不填估测"></label><label>成品尺寸<input v-model.trim="form.finished_size" placeholder="同一范围不得同时出现30cm和40cm"></label><label>商品比例<input v-model.trim="form.product_scale"></label><label>商品重量<input v-model.trim="form.weight"></label></div></fieldset>
          <fieldset class="field-group"><legend>包装与使用</legend><div class="form-grid"><label>包装内容<input v-model.trim="form.package_contents"></label><label>兼容性<input v-model.trim="form.compatibility"></label><label>安装方式<input v-model.trim="form.installation"></label><label>随附物品<input v-model.trim="form.included_items"></label><label class="wide">使用说明<textarea v-model.trim="form.usage"></textarea></label><label>玩法介绍<textarea v-model.trim="form.play"></textarea></label></div></fieldset>
          <fieldset class="field-group"><legend>版本与资料状态</legend><div class="form-grid"><label>发货地<input v-model.trim="form.ship_origin"></label><label>版本差异<input v-model.trim="form.version_difference"></label><label>图片资料状态<input v-model.trim="form.image_status"></label><label>视频资料状态<input v-model.trim="form.video_status"></label><label>图片一致性说明<input v-model.trim="form.image_match_policy" placeholder="例如：展示图仅供参考，以实际款式为准"></label><label>快递选择策略<input v-model.trim="form.courier_policy" placeholder="只填写已审核的店铺规则"></label><label>隐私包装<input v-model.trim="form.stealth_packaging"></label><label>品牌授权证据<input v-model.trim="form.authenticity_evidence" placeholder="填写可核验的授权资料，不填写口头保证"></label></div></fieldset>
          <fieldset class="field-group"><legend>回答与安全边界</legend><div class="form-grid"><label class="wide">安全提醒<textarea v-model.trim="form.safety"></textarea></label><label>禁止承诺<textarea v-model.trim="form.prohibited_promises" placeholder="例如：不得承诺固定24/48/72小时送达"></textarea></label><label>实时查询要求<textarea v-model.trim="form.realtime_lookup" placeholder="库存、价格、物流等需实时查询"></textarea></label><label class="wide">人工处理条件<textarea v-model.trim="form.manual_handling" placeholder="退款、改地址、真假授权无证据等转人工"></textarea></label><label class="wide">客户常问问题<textarea v-model.trim="form.question"></textarea></label><label class="wide">推荐回答方向<textarea v-model.trim="form.answer"></textarea></label></div></fieldset>
        </template>

        <fieldset v-else-if="form.template_type === 'SKU_DIFFERENCE'" class="field-group"><legend>SKU差异</legend><p class="group-note">每项都要写实际差异；没有差异时保留“已确认无差异”，不能留空。</p><div class="form-grid"><label>颜色款式<input v-model.trim="form.color_style" required></label><label>规格区别<input v-model.trim="form.specification_difference" required></label><label>包装区别<input v-model.trim="form.package_difference" required></label><label>数量区别<input v-model.trim="form.quantity_difference" required></label><label>尺寸区别<input v-model.trim="form.size_difference" required></label><label>玩法区别<input v-model.trim="form.play_difference" required></label><label class="wide">SKU常见问题<textarea v-model.trim="form.sku_faq"></textarea></label><label>SKU安全提醒<textarea v-model.trim="form.sku_safety"></textarea></label></div></fieldset>

        <fieldset v-else-if="form.template_type === 'FAQ'" class="field-group"><legend>常见问题与回答</legend><div class="form-grid"><label>关联基线问题<select v-model="form.related_question_id" required><option value="">请选择问题</option><option v-for="item in questionSet?.questions || []" :key="item.question_id" :value="item.question_id">{{ item.canonical_question }}</option></select></label><label class="wide">客户常问问题<textarea v-model.trim="form.question" required></textarea></label><label class="wide">标准回答<textarea v-model.trim="form.answer" required></textarea></label><label>适用场景<input v-model.trim="form.scenario" required></label><label>风险等级<select v-model="form.risk_level"><option>低</option><option>中</option><option>高</option></select></label><label>是否需要人工确认<select v-model="form.manual_confirmation"><option>否</option><option>是</option></select></label></div></fieldset>

        <fieldset v-else class="field-group"><legend>安全规则</legend><div class="form-grid"><label>关联基线问题<select v-model="form.related_question_id" required><option value="">请选择问题</option><option v-for="item in questionSet?.questions || []" :key="item.question_id" :value="item.question_id">{{ item.canonical_question }}</option></select></label><label>适用年龄<input v-model.trim="form.age"></label><label>安全主题<input v-model.trim="form.safety_topic" required></label><label>风险等级<select v-model="form.risk_level"><option>低</option><option>中</option><option>高</option></select></label><label class="wide">安全提醒<textarea v-model.trim="form.safety" required></textarea></label><label>禁止承诺内容<textarea v-model.trim="form.forbidden_claim" required></textarea></label><label>需要人工确认情况<textarea v-model.trim="form.confirmation_condition"></textarea></label><label class="wide">必须转人工情况<textarea v-model.trim="form.handoff_condition" required></textarea></label></div></fieldset>

        <aside v-if="safetyWarnings.length" class="warning-panel" aria-live="polite">
          <strong>回答安全提醒（{{ safetyWarnings.length }}）</strong>
          <article v-for="warning in safetyWarnings" :key="warning.code"><b>{{ warning.title }}</b><p>{{ warning.message }}</p></article>
          <p>可以继续保存为待审核草稿，但这些内容不会因此通过回答安全门。</p>
        </aside>
      </section>

      <section class="card editor-card source-section">
        <div class="section-heading"><span class="step">4</span><div><h2>来源与确认</h2><p>每个版本分别记录本次提交人和后续审核人。</p></div></div>
        <div class="form-grid"><label class="wide">资料来源<input v-model.trim="governance.source" required placeholder="例如：商品说明书第2页、包装警示标签"></label><label>来源日期<input v-model="governance.source_date" required type="date"></label><label>是否人工确认<select v-model="governance.confirmed"><option>是</option><option>否</option></select></label><label>本次提交人<input v-model.trim="governance.submitted_by" required placeholder="填写当前运营人员姓名或账号"></label></div>
        <p class="boundary-note">资料不足可以保存，但不得猜测。安全高风险资料必须有来源；审核通过也不等于已发布到RAG。</p>
      </section>

      <footer class="save-bar">
        <div class="completion">
          <span>必填完整度 <strong>{{ completionPercent }}%</strong></span>
          <span v-if="missingRequired.length">还缺：{{ missingRequired.join('、') }}</span>
          <span v-else>必填信息已完整，可以保存待审核草稿。</span>
          <small v-if="dirty">有未保存修改</small><small v-else>当前内容已保存或未修改</small>
        </div>
        <div class="save-actions">
          <RouterLink v-if="revisionMode" class="button secondary" :to="{ path: '/reply-readiness', query: { store: scope.store_code, product: scope.product_id, ...(scope.sku_id ? { sku: scope.sku_id } : {}), material_id: editingMaterialId, material_revision: selectedHistoryRevision } }">返回风险池并选择当前修订</RouterLink>
          <button class="button" type="submit" :disabled="submitting || missingRequired.length > 0 || (skuRequired && !scope.sku_id)">{{ submitting ? '正在保存…' : revisionMode ? '保存为新修订' : '保存并提交审核' }}</button>
        </div>
      </footer>

      <p v-if="error" class="notice error" role="alert">{{ error }}</p>
      <p v-if="receipt" class="notice success" role="status">{{ receipt }}</p>
    </form>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }.editor { display: grid; gap: 18px; }.editor-card, .revision-context { padding: 22px; }.section-heading { display: flex; align-items: center; gap: 11px; margin-bottom: 18px; }.section-heading h2, .section-heading p { margin: 0; }.section-heading h2 { color: #172554; font-size: 19px; }.section-heading p { margin-top: 4px; color: #64748b; font-size: 13px; }.step { display: grid; flex: 0 0 30px; width: 30px; height: 30px; place-items: center; border-radius: 10px; color: #fff; background: #315f9f; font-size: 13px; font-weight: 800; }
.form-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 14px; }.form-grid label { display: grid; align-content: start; gap: 6px; color: #526279; font-size: 13px; }.form-grid input, .form-grid select, .form-grid textarea { min-height: 42px; padding: 9px 10px; border: 1px solid #cbd7e6; border-radius: 8px; background: #fff; font: inherit; }.form-grid textarea { min-height: 92px; resize: vertical; }.form-grid input:focus-visible, .form-grid select:focus-visible, .form-grid textarea:focus-visible { outline: 3px solid rgb(59 130 246 / 24%); border-color: #4f7fc1; }.form-grid input:disabled, .form-grid select:disabled { color: #526279; background: #f1f4f8; }.form-grid .wide { grid-column: span 2; }
.template-tabs { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; }.template-tabs label { position: relative; display: grid; gap: 6px; padding: 14px; border: 1px solid #dbe4ef; border-radius: 10px; cursor: pointer; }.template-tabs label.active { border-color: #3973c4; background: #f4f8ff; }.template-tabs label.locked { cursor: not-allowed; opacity: .78; }.template-tabs input { position: absolute; width: 1px; height: 1px; opacity: 0; }.template-tabs label:has(input:focus-visible) { outline: 3px solid rgb(59 130 246 / 28%); }.template-tabs strong { color: #25466f; }.template-tabs span { color: #617087; font-size: 12px; line-height: 1.5; }
.knowledge-section { display: grid; gap: 18px; }.field-group { margin: 0; padding: 18px; border: 1px solid #dce5ef; border-radius: 12px; }.field-group legend { padding: 0 8px; color: #284f82; font-weight: 800; }.group-note { margin: 0 0 14px; padding: 10px 12px; border-radius: 8px; color: #5d4b19; background: #fff8df; font-size: 13px; }.warning-panel { padding: 16px; border: 1px solid #efcf82; border-radius: 12px; color: #6d4d08; background: #fff9e8; }.warning-panel > strong { display: block; margin-bottom: 10px; }.warning-panel article { padding: 9px 0; border-top: 1px solid rgb(190 145 40 / 20%); }.warning-panel article p, .warning-panel > p { margin: 4px 0 0; line-height: 1.5; }.boundary-note { margin: 16px 0 0; padding: 12px; border-radius: 9px; color: #75570a; background: #fff8df; }
.history-heading { display: flex; justify-content: space-between; gap: 14px; align-items: start; }.history-heading h2, .history-heading p { margin: 0; }.history-heading p:not(.eyebrow) { margin-top: 6px; color: #617087; }.revision-row { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 16px; }.revision-row button { padding: 7px 10px; border: 1px solid #cbd7e6; border-radius: 8px; color: #425b78; background: #fff; cursor: pointer; }.revision-row button.active { border-color: #3973c4; color: #285493; background: #edf4ff; }.revision-row button:disabled { cursor: wait; opacity: .6; }.inline-status { margin: 12px 0 0; padding: 10px 12px; border-radius: 8px; color: #385675; background: #f1f6fc; font-size: 13px; }.diff-panel { margin-top: 16px; padding: 14px; border-radius: 10px; background: #f7f9fc; }.diff-panel > div { display: flex; align-items: center; justify-content: space-between; gap: 12px; }.diff-panel article { display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 12px; padding: 11px 0; border-top: 1px solid #e0e7f0; }.diff-panel article > div { display: grid; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); gap: 10px; }.diff-panel span { overflow-wrap: anywhere; padding: 8px; border-radius: 7px; background: #fff; }.diff-panel b { align-self: center; color: #718096; }.text-button { padding: 5px 8px; border: 0; color: #285493; background: transparent; font: inherit; font-weight: 700; cursor: pointer; }
.save-bar { position: sticky; bottom: 0; z-index: 4; display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 15px 18px; border: 1px solid #cfdbea; border-radius: 13px; background: rgb(255 255 255 / 96%); box-shadow: 0 -8px 28px rgb(27 48 82 / 12%); backdrop-filter: blur(8px); }.completion { display: grid; gap: 3px; color: #526279; font-size: 13px; }.completion strong { color: #244e83; }.completion small { color: #8a5a00; }.save-actions { display: flex; gap: 10px; }.notice { margin: 0; }
@media (max-width: 900px) { .form-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }.template-tabs { grid-template-columns: repeat(2, minmax(0, 1fr)); }.save-bar { align-items: stretch; flex-direction: column; }.save-actions { justify-content: flex-end; } }
@media (max-width: 620px) { .form-grid, .template-tabs { grid-template-columns: 1fr; }.form-grid .wide { grid-column: span 1; }.history-heading { display: grid; }.history-heading .button { width: 100%; }.diff-panel article { grid-template-columns: 1fr; }.diff-panel article > div { grid-template-columns: 1fr; }.diff-panel b { transform: rotate(90deg); justify-self: center; }.save-actions { flex-direction: column; }.save-actions .button { width: 100%; }.field-group { padding: 14px; } }
</style>
