<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  apiErrorMessage,
  getKnowledgeMaterial,
  getProductKnowledgeOverview,
  getProductKnowledgeProduct,
  listKnowledgeMaterials,
  listProductKnowledgeProducts,
  reviewKnowledgeMaterial,
  uploadKnowledgeMaterial,
  type KnowledgeMaterial,
  type KnowledgeMaterialDetail,
  type KnowledgeMaterialStatus,
  type KnowledgeMaterialType,
  type KnowledgeTemplateType,
  type ProductKnowledgeDetail,
  type ProductKnowledgeListItem,
  type StoreKnowledgeSummary,
} from '../api/client'
import { displayStatus } from '../presentation'

const route = useRoute()
const stores = ref<StoreKnowledgeSummary[]>([])
const products = ref<ProductKnowledgeListItem[]>([])
const productDetail = ref<ProductKnowledgeDetail | null>(null)
const materials = ref<KnowledgeMaterial[]>([])
const selected = ref<KnowledgeMaterialDetail | null>(null)
const revisionSource = ref<KnowledgeMaterial | null>(null)
const loading = ref(false)
const catalogLoading = ref(false)
const submitting = ref(false)
const reviewing = ref(false)
const listError = ref('')
const formError = ref('')
const receipt = ref('')
const file = ref<File | null>(null)
const filters = reactive({ store_code: '', product_id: '', material_status: '' as KnowledgeMaterialStatus | '' })
const form = reactive({
  store_code: '', product_id: '', sku_id: '', material_type: 'PRODUCT_SPEC' as KnowledgeMaterialType,
  template_type: 'PRODUCT_KNOWLEDGE' as KnowledgeTemplateType,
  display_name: '', submitted_by: '', material_id: '',
})
const review = reactive({ reviewed_by: '', review_note: '' })
const templateTypes: Array<{ value: KnowledgeTemplateType; materialType: KnowledgeMaterialType }> = [
  { value: 'PRODUCT_KNOWLEDGE', materialType: 'PRODUCT_SPEC' },
  { value: 'SKU_DIFFERENCE', materialType: 'PRODUCT_SPEC' },
  { value: 'FAQ', materialType: 'FAQ_SOURCE' },
  { value: 'SAFETY_RULE', materialType: 'SAFETY_INSTRUCTION' },
  { value: 'AI_FEEDBACK', materialType: 'OTHER' },
  { value: 'KNOWLEDGE_GAP', materialType: 'OTHER' },
]
const statuses: KnowledgeMaterialStatus[] = ['RECEIVED', 'RECOGNIZED', 'REVIEWING', 'APPROVED_FOR_ANALYSIS', 'ANALYZING', 'ANALYZED', 'ANALYSIS_FAILED', 'REJECTED']

const formProducts = computed(() => products.value.filter((item) => item.technical_details.store_code === form.store_code))
const filterProducts = computed(() => products.value.filter((item) => !filters.store_code || item.technical_details.store_code === filters.store_code))

function storeName(storeCode: string): string {
  return stores.value.find((item) => item.technical_details.store_code === storeCode)?.store_name || '未找到店铺名称'
}

function productName(productId: string): string {
  return products.value.find((item) => item.technical_details.product_id === productId)?.product_name || '未找到商品名称'
}

function skuName(skuId: string | null): string {
  if (!skuId) return '全部 SKU'
  return productDetail.value?.skus.find((item) => item.technical_details.sku_id === skuId)?.sku_name || '指定 SKU'
}

function materialStatusLabel(item: KnowledgeMaterial): string {
  if (item.material_status === 'APPROVED_FOR_ANALYSIS'
    && (item.recognition_summary.template_type === 'AI_FEEDBACK' || item.recognition_summary.template_type === 'KNOWLEDGE_GAP')) {
    return '审核通过'
  }
  return displayStatus(item.material_status)
}

async function loadCatalog(): Promise<void> {
  catalogLoading.value = true
  try {
    const [overview, productPage] = await Promise.all([
      getProductKnowledgeOverview(),
      listProductKnowledgeProducts(),
    ])
    stores.value = overview.stores
    products.value = productPage.items
    const requestedStore = typeof route.query.store === 'string' ? route.query.store : ''
    const requestedProduct = typeof route.query.product === 'string' ? route.query.product : ''
    const selectedStoreCode = requestedStore
    if (selectedStoreCode && stores.value.some((item) => item.technical_details.store_code === selectedStoreCode)) {
      form.store_code = selectedStoreCode
      filters.store_code = selectedStoreCode
    }
    if (requestedProduct && products.value.some((item) => item.technical_details.product_id === requestedProduct)) {
      form.product_id = requestedProduct
      filters.product_id = requestedProduct
      await loadProductDetail(requestedProduct)
    }
  } catch (reason: unknown) {
    listError.value = `商品目录读取失败：${apiErrorMessage(reason)}`
  } finally {
    catalogLoading.value = false
  }
}

async function loadProductDetail(productId: string): Promise<void> {
  productDetail.value = productId ? await getProductKnowledgeProduct(productId) : null
}

async function onFormStoreChange(): Promise<void> {
  form.product_id = ''
  form.sku_id = ''
  productDetail.value = null
}

async function onFormProductChange(): Promise<void> {
  form.sku_id = ''
  formError.value = ''
  try {
    await loadProductDetail(form.product_id)
  } catch (reason: unknown) {
    productDetail.value = null
    formError.value = apiErrorMessage(reason)
  }
}

function onFilterStoreChange(): void {
  filters.product_id = ''
}

async function load(): Promise<void> {
  loading.value = true
  listError.value = ''
  try {
    const result = await listKnowledgeMaterials(filters)
    materials.value = result.items
    if (selected.value && !result.items.some((item) => item.material_id === selected.value?.material_id)) selected.value = null
  } catch (reason: unknown) {
    materials.value = []
    selected.value = null
    listError.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

async function choose(item: KnowledgeMaterial): Promise<void> {
  listError.value = ''
  try {
    selected.value = await getKnowledgeMaterial(item.material_id)
  } catch (reason: unknown) {
    selected.value = null
    listError.value = apiErrorMessage(reason)
  }
}

async function prepareRevision(item: KnowledgeMaterial): Promise<void> {
  revisionSource.value = item
  form.material_id = item.material_id
  form.store_code = item.store_code
  form.product_id = item.product_id
  form.sku_id = item.sku_id || ''
  form.display_name = item.display_name
  form.material_type = item.material_type
  form.template_type = item.recognition_summary.template_type || 'PRODUCT_KNOWLEDGE'
  onTemplateTypeChange()
  await onFormProductChange()
  form.sku_id = item.sku_id || ''
}

function cancelRevision(): void {
  revisionSource.value = null
  form.material_id = ''
}

function onFileChange(event: Event): void {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
  formError.value = ''
  receipt.value = ''
}

function onTemplateTypeChange(): void {
  form.material_type = templateTypes.find((item) => item.value === form.template_type)?.materialType || 'OTHER'
}

async function submit(): Promise<void> {
  if (!file.value || submitting.value) return
  submitting.value = true
  formError.value = ''
  receipt.value = ''
  try {
    const result = await uploadKnowledgeMaterial(file.value, form)
    receipt.value = `资料已识别并进入人工审核流程，共识别 ${result.recognition_summary.record_count || 1} 条记录。`
    file.value = null
    cancelRevision()
    await load()
  } catch (reason: unknown) {
    formError.value = apiErrorMessage(reason)
  } finally {
    submitting.value = false
  }
}

async function reviewSelected(decision: 'APPROVE_FOR_ANALYSIS' | 'REJECT'): Promise<void> {
  if (!selected.value || reviewing.value) return
  reviewing.value = true
  formError.value = ''
  try {
    await reviewKnowledgeMaterial(selected.value.material_id, {
      revision: selected.value.revision,
      decision,
      reviewed_by: review.reviewed_by,
      review_note: review.review_note,
    })
    await load()
    selected.value = await getKnowledgeMaterial(selected.value.material_id)
  } catch (reason: unknown) {
    formError.value = apiErrorMessage(reason)
  } finally {
    reviewing.value = false
  }
}

onMounted(async () => {
  await loadCatalog()
  await load()
})
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">商品知识补充</p>
        <h1>资料上传与审核</h1>
        <p>先选择业务店铺、商品和 SKU，再上传已核实资料。审核通过只允许进入 AI 质量分析，不会自动发布知识。</p>
      </div>
      <RouterLink class="button secondary" to="/import-center">下载中文资料模板</RouterLink>
    </div>

    <section class="card guide">
      <h2>三步完成资料补充</h2>
      <ol>
        <li>从完整中文名称中选择店铺、商品和 SKU，不需要填写技术编号。</li>
        <li>上传只含商品事实的资料；不要包含客户姓名、电话、地址、订单或支付信息。</li>
        <li>核对识别摘要并人工审核。审核通过不等于激活或发布到 RAG。</li>
      </ol>
    </section>

    <p v-if="catalogLoading" class="notice" role="status">正在读取店铺和商品目录…</p>

    <section class="work-grid">
      <form class="card upload-form" @submit.prevent="submit">
        <h2>{{ revisionSource ? '创建资料修订版本' : '上传新资料' }}</h2>
        <p v-if="revisionSource" class="notice">正在为“{{ revisionSource.display_name }}”补充新的修订资料。<button class="text-button" type="button" @click="cancelRevision">取消修订</button></p>
        <label>店铺
          <select v-model="form.store_code" required @change="onFormStoreChange">
            <option value="">请选择店铺</option>
            <option v-for="store in stores" :key="store.technical_details.store_code || store.store_name" :value="store.technical_details.store_code || ''">{{ store.store_name }}</option>
          </select>
        </label>
        <label>商品
          <select v-model="form.product_id" required :disabled="!form.store_code" @change="onFormProductChange">
            <option value="">请选择商品</option>
            <option v-for="product in formProducts" :key="product.technical_details.product_id || product.product_name" :value="product.technical_details.product_id || ''">{{ product.product_name }}</option>
          </select>
        </label>
        <label>SKU（可选）
          <select v-model="form.sku_id" :disabled="!form.product_id">
            <option value="">适用于全部 SKU</option>
            <option v-for="sku in productDetail?.skus || []" :key="sku.technical_details.sku_id || sku.sku_name" :value="sku.technical_details.sku_id || ''">{{ sku.sku_name }}{{ sku.specification_difference ? ` · ${sku.specification_difference}` : '' }}</option>
          </select>
        </label>
        <label>模板类型<select v-model="form.template_type" @change="onTemplateTypeChange"><option v-for="type in templateTypes" :key="type.value" :value="type.value">{{ displayStatus(type.value) }}</option></select></label>
        <label>资料名称<input v-model.trim="form.display_name" required maxlength="256" placeholder="例如：Q66 消防局积木拼装说明"></label>
        <label>提交人<input v-model.trim="form.submitted_by" required maxlength="128" placeholder="填写运营人员姓名或账号"></label>
        <label>资料文件<input type="file" accept=".xlsx,.json" required @change="onFileChange"><small>上传对应中文 Excel 模板；结构化快速补充会使用受控 JSON，单个文件最大 5 MB。</small></label>
        <p class="notice boundary">系统只保存在受控运行目录；不会自动脱敏、发布知识、训练模型、修改 Prompt 或向客户发送消息。</p>
        <p v-if="formError" class="notice error" role="alert">{{ formError }}</p>
        <p v-if="receipt" class="notice success" role="status">{{ receipt }}</p>
        <button class="button" :disabled="submitting || !file || !form.store_code || !form.product_id" type="submit">{{ submitting ? '正在识别资料…' : revisionSource ? '上传修订并识别' : '上传并识别' }}</button>
      </form>

      <section class="card materials">
        <div class="section-heading"><div><h2>资料记录</h2><p>只展示运营需要的业务名称、模板类型、识别结果和审核状态。</p></div><button class="button secondary" type="button" @click="load">刷新</button></div>
        <form class="filters" @submit.prevent="load">
          <label>店铺<select v-model="filters.store_code" @change="onFilterStoreChange"><option value="">全部店铺</option><option v-for="store in stores" :key="`filter-${store.store_name}`" :value="store.technical_details.store_code || ''">{{ store.store_name }}</option></select></label>
          <label>商品<select v-model="filters.product_id"><option value="">全部商品</option><option v-for="product in filterProducts" :key="`filter-${product.product_name}`" :value="product.technical_details.product_id || ''">{{ product.product_name }}</option></select></label>
          <label>状态<select v-model="filters.material_status"><option value="">全部状态</option><option v-for="status in statuses" :key="status" :value="status">{{ displayStatus(status) }}</option></select></label>
          <button class="button secondary" type="submit">筛选</button>
        </form>
        <p v-if="loading" class="notice" role="status">正在读取资料记录…</p>
        <p v-else-if="listError" class="notice error" role="alert">{{ listError }}</p>
        <p v-else-if="materials.length === 0" class="notice">当前没有符合条件的资料记录。</p>
        <div v-else class="material-list">
          <article v-for="item in materials" :key="`${item.material_id}-${item.revision}`" class="material-card">
            <div class="material-heading"><button class="link-button" type="button" @click="choose(item)">{{ item.display_name }}</button><span class="badge">{{ materialStatusLabel(item) }}</span></div>
            <strong>{{ storeName(item.store_code) }} → {{ productName(item.product_id) }} → {{ skuName(item.sku_id) }}</strong>
            <p>模板：{{ item.recognition_summary.template_name || displayStatus(item.material_type) }} · {{ item.recognition_summary.record_count || 1 }} 条记录</p>
            <p>已识别：{{ item.recognition_summary.detected_fields.join('、') || '尚未识别到字段' }}</p>
            <p v-if="item.recognition_summary.missing_expected_fields.length" class="warning">待补充：{{ item.recognition_summary.missing_expected_fields.join('、') }}</p>
            <div class="material-actions"><button class="text-button" type="button" @click="choose(item)">查看并审核</button><button class="text-button" type="button" @click="prepareRevision(item)">以此资料创建修订版本</button></div>
          </article>
        </div>
      </section>
    </section>

    <section v-if="selected" class="card review-panel">
      <div class="section-heading"><div><h2>人工核对：{{ selected.display_name }}</h2><p>{{ storeName(selected.store_code) }} → {{ productName(selected.product_id) }} → {{ skuName(selected.sku_id) }}</p></div><span class="badge">{{ materialStatusLabel(selected) }}</span></div>
      <div class="review-grid">
        <div><h3>识别摘要</h3><p><strong>已识别：</strong>{{ selected.recognition_summary.detected_fields.join('、') || '尚未识别到字段' }}</p><p><strong>待补充：</strong>{{ selected.recognition_summary.missing_expected_fields.join('、') || '暂无明显缺口' }}</p><p class="notice boundary">{{ selected.recognition_summary.privacy_reminder }}</p><h3>核对摘要</h3><pre>{{ selected.analysis_text_preview }}</pre></div>
        <div v-if="selected.material_status === 'RECOGNIZED'" class="review-form"><h3>审核决定</h3><label>审核人<input v-model.trim="review.reviewed_by" maxlength="128" placeholder="填写运营人员姓名或账号"></label><label>审核备注<textarea v-model.trim="review.review_note" maxlength="4000" placeholder="说明已核对的来源、缺口或拒绝原因"></textarea></label><p v-if="selected.recognition_summary.warnings.length" class="notice boundary">{{ selected.recognition_summary.warnings.join('；') }}</p><button class="button" type="button" :disabled="reviewing || !review.reviewed_by || !review.review_note" @click="reviewSelected('APPROVE_FOR_ANALYSIS')">{{ reviewing ? '提交中…' : '审核通过' }}</button><button class="button secondary" type="button" :disabled="reviewing || !review.reviewed_by || !review.review_note" @click="reviewSelected('REJECT')">拒绝本次资料</button></div>
        <div v-else><h3>审核记录</h3><p>{{ selected.review_note || '该资料尚未记录审核备注。' }}</p><p>资料来源文件：{{ selected.original_filename }}</p><p class="notice boundary">审核通过只表示运营已核对资料，不等于发布到 RAG，也不触发模型训练。</p></div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }.guide { margin-bottom: 20px; background: #f8fbff; }.guide h2, .upload-form h2, .materials h2, .review-panel h2 { margin-top: 0; color: #172554; }.guide li { margin: 8px 0; line-height: 1.6; }.work-grid, .review-grid { display: grid; grid-template-columns: minmax(290px, .8fr) minmax(0, 1.45fr); gap: 20px; }.upload-form, .review-form { display: grid; align-content: start; gap: 12px; }.upload-form label, .filters label, .review-form label { display: grid; gap: 6px; color: #526279; font-size: 13px; }.upload-form input, .upload-form select, .review-form input, .review-form textarea, .filters select { min-height: 40px; padding: 8px; border: 1px solid #cbd7e6; border-radius: 7px; font: inherit; }.review-form textarea { min-height: 108px; resize: vertical; }.upload-form small { display: block; margin-top: 4px; color: #64748b; }.boundary { color: #75570a; background: #fff8df; line-height: 1.55; }.section-heading, .material-heading { display: flex; justify-content: space-between; gap: 16px; align-items: start; }.section-heading p { margin: 5px 0 0; color: #617087; }.filters { display: flex; flex-wrap: wrap; align-items: end; gap: 10px; margin: 18px 0; }.filters label { min-width: 160px; }.material-list { display: grid; gap: 10px; }.material-card { padding: 14px; border: 1px solid #dbe4ef; border-radius: 10px; }.material-card > strong { display: block; margin-top: 8px; color: #334965; font-size: 13px; }.material-card p { margin: 7px 0 0; color: #617087; font-size: 13px; }.material-card .warning { color: #a56618; }.material-actions { display: flex; flex-wrap: wrap; gap: 12px; margin-top: 10px; }.link-button, .text-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; text-align: left; cursor: pointer; }.link-button { font-weight: 700; }.text-button { font-size: 13px; }.review-panel { margin-top: 20px; }.review-grid { grid-template-columns: minmax(0, 1.35fr) minmax(260px, .75fr); }.review-grid h3 { margin-top: 0; color: #25466f; }.review-grid p, pre { line-height: 1.6; overflow-wrap: anywhere; white-space: pre-wrap; }pre { max-height: 330px; margin: 0; padding: 12px; overflow: auto; border-radius: 8px; background: #f4f7fb; font-size: 13px; }
@media (max-width: 980px) { .work-grid, .review-grid { grid-template-columns: 1fr; } }
</style>
