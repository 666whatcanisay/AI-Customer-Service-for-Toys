<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import {
  apiErrorMessage,
  getProductKnowledgeImportMergePreview,
  getProductKnowledgeImportPreflight,
  listOperationStores,
  reviewProductKnowledgeImport,
  uploadProductKnowledgeImport,
  type ProductKnowledgeImportChangeType,
  type ProductKnowledgeImportMergePreview,
  type ProductKnowledgeImportPreflight,
  type ProductKnowledgeImportPreviewItem,
  type ProductKnowledgeImportTemplateType,
  type StoreOperationItem,
} from '../api/client'

const route = useRoute()
const stores = ref<StoreOperationItem[]>([])
const selectedStoreRef = ref('')
const templateType = ref<ProductKnowledgeImportTemplateType>('PRODUCT_KNOWLEDGE')
const operator = ref('')
const file = ref<File | null>(null)
const loadingStores = ref(true)
const submitting = ref(false)
const reviewingChangeSet = ref('')
const errorMessage = ref('')
const successMessage = ref('')
const batchId = ref('')
const preflight = ref<ProductKnowledgeImportPreflight | null>(null)
const preview = ref<ProductKnowledgeImportMergePreview | null>(null)
const uploadIdempotencyKey = ref('')
const reviewNotes = reactive<Record<string, string>>({})
const reviewKeys = reactive<Record<string, string>>({})

const templates: Array<{
  value: ProductKnowledgeImportTemplateType
  label: string
  supported: boolean
}> = [
  { value: 'PRODUCT_KNOWLEDGE', label: '商品知识采集模板', supported: true },
  { value: 'SKU_DIFFERENCE', label: 'SKU差异知识采集模板', supported: false },
  { value: 'FAQ', label: '客服FAQ知识采集模板', supported: false },
  { value: 'SAFETY_RULE', label: '商品安全规则采集模板', supported: false },
  { value: 'AI_FEEDBACK', label: '客服AI问题反馈模板', supported: false },
  { value: 'KNOWLEDGE_GAP', label: 'AI知识缺口管理模板', supported: false },
]

const selectedStore = computed(() => stores.value.find(
  (item) => String(item.store_ref) === selectedStoreRef.value,
))
const selectedTemplate = computed(() => templates.find((item) => item.value === templateType.value))
const reviewableItems = computed(() => preview.value?.items.filter(
  (item) => item.product.status === 'IDENTIFIED_PENDING_REVIEW',
) || [])

function newIdempotencyKey(prefix: string): string {
  return typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
    ? `${prefix}-${crypto.randomUUID()}`
    : `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2)}`
}

function resetUploadKey(): void {
  uploadIdempotencyKey.value = ''
  errorMessage.value = ''
  successMessage.value = ''
}

function onTemplateChange(): void {
  resetUploadKey()
  if (!selectedTemplate.value?.supported) {
    window.alert('该模板导入功能暂未开放')
  }
}

function onFileChange(event: Event): void {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
  resetUploadKey()
}

async function loadStores(): Promise<void> {
  loadingStores.value = true
  try {
    stores.value = (await listOperationStores()).items.filter((item) => item.status === 'ACTIVE')
    const requested = typeof route.query.store_ref === 'string' ? route.query.store_ref : ''
    const remembered = sessionStorage.getItem('c-operation-import-store-ref') || ''
    const candidate = requested || remembered
    if (stores.value.some((item) => String(item.store_ref) === candidate)) {
      selectedStoreRef.value = candidate
    }
  } catch (reason: unknown) {
    stores.value = []
    errorMessage.value = `店铺读取失败：${apiErrorMessage(reason)}`
  } finally {
    loadingStores.value = false
  }
}

async function loadBatch(id: string): Promise<void> {
  try {
    const [preflightResult, previewResult] = await Promise.all([
      getProductKnowledgeImportPreflight(id),
      getProductKnowledgeImportMergePreview(id),
    ])
    batchId.value = id
    preflight.value = preflightResult
    preview.value = previewResult
    sessionStorage.setItem('r009-product-knowledge-import-batch-id', id)
  } catch (reason: unknown) {
    sessionStorage.removeItem('r009-product-knowledge-import-batch-id')
    errorMessage.value = `导入批次读取失败：${apiErrorMessage(reason)}`
  }
}

async function submit(): Promise<void> {
  if (!file.value || !selectedStore.value || submitting.value) return
  if (!selectedTemplate.value?.supported) {
    window.alert('该模板导入功能暂未开放')
    return
  }
  if (!operator.value.trim()) {
    errorMessage.value = '请填写操作人。'
    return
  }
  submitting.value = true
  errorMessage.value = ''
  successMessage.value = ''
  uploadIdempotencyKey.value ||= newIdempotencyKey('product-knowledge-upload')
  try {
    const result = await uploadProductKnowledgeImport(
      file.value,
      {
        store_ref: selectedStore.value.store_ref,
        template_type: templateType.value,
        operator: operator.value.trim(),
      },
      uploadIdempotencyKey.value,
    )
    await loadBatch(result.batch_id)
    successMessage.value = result.status === 'PREFLIGHT_FAILED'
      ? '文件已完成预检，但存在阻塞问题，请按提示修正后重新上传。'
      : result.status === 'NO_CHANGE'
        ? '文件已完成 Merge 对比，没有需要审核的变化。'
        : '文件已识别，所有新增和修改均处于“已识别待审核”，尚未写入正式商品。'
    uploadIdempotencyKey.value = ''
  } catch (reason: unknown) {
    errorMessage.value = apiErrorMessage(reason)
  } finally {
    submitting.value = false
  }
}

async function reviewItem(
  item: ProductKnowledgeImportPreviewItem,
  decision: 'APPROVE' | 'REJECT',
): Promise<void> {
  if (!batchId.value || reviewingChangeSet.value) return
  const note = (reviewNotes[item.product.change_set_id] || '').trim()
  if (!operator.value.trim()) {
    errorMessage.value = '请填写操作人后再审核。'
    return
  }
  if (decision === 'REJECT' && !note) {
    errorMessage.value = '驳回时必须填写审核备注。'
    return
  }
  const keyName = `${item.product.change_set_id}:${decision}`
  reviewKeys[keyName] ||= newIdempotencyKey(`product-knowledge-${decision.toLowerCase()}`)
  reviewingChangeSet.value = item.product.change_set_id
  errorMessage.value = ''
  successMessage.value = ''
  try {
    const receipt = await reviewProductKnowledgeImport(
      batchId.value,
      item.product.change_set_id,
      {
        decision,
        operator: operator.value.trim(),
        review_note: note || null,
        expected_base_snapshot_hash: item.product.base_snapshot_hash,
        expected_change_set_version: item.product.version,
      },
      reviewKeys[keyName],
    )
    delete reviewKeys[keyName]
    successMessage.value = receipt.outcome === 'APPLIED'
      ? `“${item.product.product_name}”已审核通过并完成字段级 Merge。`
      : receipt.outcome === 'REJECTED'
        ? `“${item.product.product_name}”已驳回，正式商品未修改。`
        : '正式商品已变化，本次审核未写入，请重新上传并核对。'
    await loadBatch(batchId.value)
  } catch (reason: unknown) {
    errorMessage.value = apiErrorMessage(reason)
  } finally {
    reviewingChangeSet.value = ''
  }
}

function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}

const changeTypeLabels: Record<ProductKnowledgeImportChangeType, string> = {
  ADD: '新增',
  UPDATE: '更新',
  KEEP: '保留原值',
  NO_CHANGE: '无变化',
}

const statusLabels: Record<string, string> = {
  IDENTIFIED_PENDING_REVIEW: '已识别待审核',
  NO_CHANGE: '无变化',
  APPROVED_APPLIED: '已通过并写入',
  REJECTED: '已驳回',
  STALE_REVIEW_REQUIRED: '数据已变化，需重新审核',
  APPLY_FAILED: '写入失败',
  PREFLIGHT_FAILED: '预检未通过',
  PARTIALLY_REVIEWED: '部分已审核',
  COMPLETED: '审核完成',
}

watch(selectedStoreRef, (value) => {
  if (value) sessionStorage.setItem('c-operation-import-store-ref', value)
  else sessionStorage.removeItem('c-operation-import-store-ref')
  resetUploadKey()
})

onMounted(async () => {
  await loadStores()
  const rememberedBatch = sessionStorage.getItem('r009-product-knowledge-import-batch-id')
  if (rememberedBatch) await loadBatch(rememberedBatch)
})
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <p class="eyebrow">R009 · 商品知识批量维护</p>
        <h1>资料上传与审核</h1>
        <p>选择店铺与固定模板，上传 Excel 生成字段级 Merge 预览；只有人工审核通过的商品才写入正式业务数据。</p>
      </div>
      <RouterLink class="button secondary" to="/import-center">下载六类 Excel 模板</RouterLink>
    </div>

    <section class="card boundary-card">
      <strong>安全边界</strong>
      <p>Excel 不覆盖数据库、不删除原字段。审核前正式数据零写入；审核通过也不会自动发布 RAG、修改 Prompt、激活客服或执行任何业务动作。</p>
    </section>

    <form class="card import-form" @submit.prevent="submit">
      <ol class="step-list">
        <li :class="{ active: !selectedStoreRef, done: !!selectedStoreRef }"><span>1</span><strong>选择店铺</strong></li>
        <li :class="{ active: !!selectedStoreRef && !templateType, done: !!templateType }"><span>2</span><strong>选择模板</strong></li>
        <li :class="{ active: !!selectedStoreRef && !!templateType, done: !!batchId }"><span>3</span><strong>上传并审核</strong></li>
      </ol>

      <div class="form-grid">
        <label>Step 1 · 目标业务店铺
          <select v-model="selectedStoreRef" required :disabled="loadingStores">
            <option value="">请选择店铺</option>
            <option v-for="store in stores" :key="store.store_ref" :value="String(store.store_ref)">
              {{ store.store_name }} · {{ store.platform_name }}
            </option>
          </select>
          <small v-if="selectedStore">Excel 中每行店铺名称必须与“{{ selectedStore.store_name }}”一致。</small>
        </label>

        <label>Step 2 · 导入模板类型
          <select v-model="templateType" required @change="onTemplateChange">
            <option v-for="template in templates" :key="template.value" :value="template.value">
              {{ template.label }} · {{ template.supported ? '已支持' : '开发中' }}
            </option>
          </select>
          <small v-if="!selectedTemplate?.supported" class="warning">该模板导入功能暂未开放</small>
        </label>

        <label>操作人
          <input v-model.trim="operator" required maxlength="128" placeholder="填写运营人员姓名或账号">
          <small>用于生成上传与审核收据，不代替登录鉴权。</small>
        </label>

        <label>Step 3 · 商品知识 Excel
          <input type="file" accept=".xlsx" required @change="onFileChange">
          <small>仅解析“商品知识采集模板 V1.xlsx”的四个固定工作表，不调用 AI。</small>
        </label>
      </div>

      <p v-if="loadingStores" class="notice" role="status">正在读取可用店铺…</p>
      <p v-if="errorMessage" class="notice error" role="alert">{{ errorMessage }}</p>
      <p v-if="successMessage" class="notice success" role="status">{{ successMessage }}</p>
      <button
        class="button"
        type="submit"
        :disabled="submitting || !file || !selectedStore || !selectedTemplate?.supported || !operator"
      >
        {{ submitting ? '正在解析并生成 Merge 预览…' : '上传 Excel 并生成待审核结果' }}
      </button>
    </form>

    <section v-if="preflight" class="card preflight-card">
      <div class="section-heading">
        <div><p class="eyebrow">Batch {{ preflight.batch_id }}</p><h2>文件预检结果</h2></div>
        <span class="badge">{{ statusLabels[preflight.status] || preflight.status }}</span>
      </div>
      <div class="summary-grid">
        <div><strong>{{ preflight.field_validation_result.data_row_count || 0 }}</strong><span>数据行</span></div>
        <div><strong>{{ preflight.product_identification_result.new_count || 0 }}</strong><span>新增商品</span></div>
        <div><strong>{{ preflight.product_identification_result.existing_count || 0 }}</strong><span>已有商品</span></div>
        <div><strong>{{ preflight.field_validation_result.blocking_issue_count || 0 }}</strong><span>阻塞问题</span></div>
      </div>
      <div class="sheet-grid">
        <span v-for="sheet in preflight.sheet_results" :key="sheet.sheet_name" :class="['sheet-chip', { invalid: !sheet.valid }]">
          {{ sheet.sheet_name }} · {{ sheet.valid ? '通过' : '异常' }}
        </span>
      </div>
      <ul v-if="preflight.field_validation_result.issues?.length" class="issue-list">
        <li v-for="(issue, index) in preflight.field_validation_result.issues" :key="`${issue.code}-${index}`">
          {{ issue.message }}
        </li>
      </ul>
    </section>

    <section v-if="preview" class="review-area">
      <div class="section-heading review-heading">
        <div><p class="eyebrow">字段级增量合并</p><h2>Merge 审核结果</h2><p>旧值用于核对，Excel 空值只会保留原值，不会清空数据库。</p></div>
        <span class="badge">待审核 {{ reviewableItems.length }} 个商品</span>
      </div>

      <p v-if="preview.items.length === 0" class="card notice">当前批次没有可展示的商品变更。</p>
      <article v-for="item in preview.items" :key="item.product.change_set_id" class="card change-card">
        <div class="change-heading">
          <div><h3>{{ item.product.product_name }}</h3><p>{{ item.product.operation === 'CREATE' ? '新增商品候选' : item.product.operation === 'UPDATE' ? '已有商品字段更新候选' : '商品数据无变化' }}</p></div>
          <span class="badge">{{ statusLabels[item.product.status] || item.product.status }}</span>
        </div>

        <div class="table-wrap">
          <table>
            <thead><tr><th>字段</th><th>旧值</th><th>Excel 值</th><th>合并后值</th><th>变化类型</th></tr></thead>
            <tbody>
              <tr v-for="field in item.fields" :key="field.field_key">
                <td><strong>{{ field.field_label }}</strong></td>
                <td>{{ formatValue(field.old_value) }}</td>
                <td>{{ formatValue(field.incoming_value) }}</td>
                <td>{{ formatValue(field.merged_value) }}</td>
                <td><span :class="['change-badge', field.change_type.toLowerCase()]">{{ changeTypeLabels[field.change_type] }}</span></td>
              </tr>
            </tbody>
          </table>
        </div>

        <div v-if="item.product.status === 'IDENTIFIED_PENDING_REVIEW'" class="review-actions">
          <label>审核备注
            <textarea v-model.trim="reviewNotes[item.product.change_set_id]" maxlength="4000" placeholder="通过时可记录核对依据；驳回时必须说明原因。"></textarea>
          </label>
          <div>
            <button class="button" type="button" :disabled="!!reviewingChangeSet" @click="reviewItem(item, 'APPROVE')">
              {{ reviewingChangeSet === item.product.change_set_id ? '提交中…' : '通过并 Merge' }}
            </button>
            <button class="button secondary" type="button" :disabled="!!reviewingChangeSet" @click="reviewItem(item, 'REJECT')">驳回</button>
          </div>
        </div>
      </article>
    </section>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.boundary-card { margin-bottom: 18px; border-left: 4px solid #d59b2c; background: #fffaf0; }
.boundary-card p { margin-bottom: 0; color: #526279; line-height: 1.65; }
.import-form { margin-bottom: 20px; }
.step-list { display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 0 0 24px; padding: 0; list-style: none; }
.step-list li { display: flex; gap: 9px; align-items: center; padding: 12px; border: 1px solid #dbe4ef; border-radius: 10px; color: #718096; background: #f8fafc; }
.step-list span { display: grid; width: 26px; height: 26px; place-items: center; border-radius: 50%; background: #e2e8f0; font-size: 12px; }
.step-list li.active { border-color: #8cb2e8; color: #244d83; background: #f3f8ff; }
.step-list li.done { color: #217447; }
.step-list li.done span { color: #fff; background: #369367; }
.form-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }
.form-grid label, .review-actions label { display: grid; gap: 7px; color: #43566f; font-size: 13px; font-weight: 700; }
.form-grid input, .form-grid select, .review-actions textarea { min-height: 42px; padding: 9px 10px; border: 1px solid #cbd7e6; border-radius: 8px; background: #fff; font: inherit; }
.form-grid small { color: #6b7a90; font-weight: 400; line-height: 1.5; }
.form-grid small.warning { color: #a4610c; font-weight: 700; }
.import-form > .button { margin-top: 18px; }
.section-heading, .change-heading { display: flex; justify-content: space-between; gap: 18px; align-items: start; }
.section-heading h2, .change-heading h3 { margin: 0; color: #172554; }
.section-heading p, .change-heading p { color: #617087; }
.badge { display: inline-flex; padding: 5px 9px; border-radius: 999px; color: #285282; background: #eaf2ff; font-size: 12px; font-weight: 800; white-space: nowrap; }
.summary-grid { display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px; margin: 18px 0; }
.summary-grid div { display: grid; gap: 4px; padding: 14px; border-radius: 10px; background: #f5f8fc; }
.summary-grid strong { color: #173f72; font-size: 24px; }.summary-grid span { color: #617087; font-size: 12px; }
.sheet-grid { display: flex; flex-wrap: wrap; gap: 8px; }.sheet-chip { padding: 6px 9px; border-radius: 7px; color: #217447; background: #ecf9f1; font-size: 12px; font-weight: 700; }.sheet-chip.invalid { color: #a33a2b; background: #fff0ed; }
.issue-list { color: #9b3d2e; line-height: 1.7; }
.review-area { margin-top: 24px; }.review-heading { margin-bottom: 14px; }.change-card { margin-bottom: 16px; }
.table-wrap { overflow-x: auto; margin-top: 14px; }table { width: 100%; border-collapse: collapse; font-size: 13px; }th, td { min-width: 145px; padding: 11px; border-bottom: 1px solid #e5ebf2; text-align: left; vertical-align: top; white-space: pre-wrap; }th { color: #425672; background: #f7f9fc; }td:first-child { min-width: 120px; color: #243b5a; }
.change-badge { display: inline-flex; padding: 4px 7px; border-radius: 6px; font-size: 12px; font-weight: 800; }.change-badge.add { color: #17633a; background: #e8f7ee; }.change-badge.update { color: #8a4d00; background: #fff2da; }.change-badge.keep { color: #4d5d73; background: #edf1f5; }.change-badge.no_change { color: #526279; background: #f3f5f7; }
.review-actions { display: grid; grid-template-columns: minmax(0, 1fr) auto; gap: 14px; align-items: end; margin-top: 16px; padding-top: 16px; border-top: 1px solid #e5ebf2; }.review-actions textarea { min-height: 78px; resize: vertical; }.review-actions > div { display: flex; gap: 9px; }
@media (max-width: 800px) { .form-grid, .summary-grid { grid-template-columns: 1fr 1fr; }.review-actions { grid-template-columns: 1fr; } }
@media (max-width: 560px) { .step-list, .form-grid, .summary-grid { grid-template-columns: 1fr; }.section-heading, .change-heading { display: grid; } }
</style>
