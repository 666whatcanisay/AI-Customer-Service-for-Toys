<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'

import {
  apiErrorMessage,
  getKnowledgeMaterial,
  listKnowledgeMaterials,
  reviewKnowledgeMaterial,
  uploadKnowledgeMaterial,
  type KnowledgeMaterial,
  type KnowledgeMaterialDetail,
  type KnowledgeMaterialStatus,
  type KnowledgeMaterialType,
} from '../api/client'
import { displayStatus } from '../presentation'

const materials = ref<KnowledgeMaterial[]>([])
const selected = ref<KnowledgeMaterialDetail | null>(null)
const loading = ref(false)
const submitting = ref(false)
const reviewing = ref(false)
const listError = ref('')
const formError = ref('')
const receipt = ref('')
const file = ref<File | null>(null)
const filters = reactive({ store_code: '', product_id: '', material_status: '' as KnowledgeMaterialStatus | '' })
const form = reactive({
  store_code: '', product_id: '', sku_id: '', material_type: 'PRODUCT_SPEC' as KnowledgeMaterialType,
  display_name: '', submitted_by: '', material_id: '',
})
const review = reactive({ reviewed_by: '', review_note: '' })
const materialTypes: KnowledgeMaterialType[] = ['PRODUCT_SPEC', 'SAFETY_INSTRUCTION', 'ASSEMBLY_GUIDE', 'FAQ_SOURCE', 'OTHER']
const statuses: KnowledgeMaterialStatus[] = ['RECOGNIZED', 'APPROVED_FOR_ANALYSIS', 'ANALYZING', 'ANALYZED', 'ANALYSIS_FAILED', 'REJECTED']

async function load(): Promise<void> {
  loading.value = true
  listError.value = ''
  try {
    const result = await listKnowledgeMaterials(filters)
    materials.value = result.items
    if (selected.value) {
      const current = result.items.find((item) => item.material_id === selected.value?.material_id)
      if (!current) selected.value = null
    }
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
    form.material_id = item.material_id
  } catch (reason: unknown) {
    selected.value = null
    listError.value = apiErrorMessage(reason)
  }
}

function onFileChange(event: Event): void {
  file.value = (event.target as HTMLInputElement).files?.[0] ?? null
  formError.value = ''
  receipt.value = ''
}

async function submit(): Promise<void> {
  if (!file.value || submitting.value) return
  submitting.value = true
  formError.value = ''
  receipt.value = ''
  try {
    const result = await uploadKnowledgeMaterial(file.value, form)
    receipt.value = `资料已识别：${result.material_id}（版本 ${result.revision}）。下一步请在右侧核对识别摘要，再人工审核。`
    file.value = null
    await load()
  } catch (reason: unknown) {
    formError.value = apiErrorMessage(reason)
  } finally {
    submitting.value = false
  }
}

async function approve(): Promise<void> {
  if (!selected.value || reviewing.value) return
  reviewing.value = true
  formError.value = ''
  try {
    await reviewKnowledgeMaterial(selected.value.material_id, {
      revision: selected.value.revision,
      decision: 'APPROVE_FOR_ANALYSIS',
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

async function reject(): Promise<void> {
  if (!selected.value || reviewing.value) return
  reviewing.value = true
  formError.value = ''
  try {
    await reviewKnowledgeMaterial(selected.value.material_id, {
      revision: selected.value.revision,
      decision: 'REJECT',
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

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <h1>商品资料上传与审核</h1>
        <p>把已核实的商品资料交给系统识别，再由运营人工审核。上传或分析成功都不等于已发布到 AI 知识库。</p>
      </div>
      <RouterLink class="button secondary" to="/import-center">下载资料模板</RouterLink>
    </div>

    <section class="card guide">
      <h2>三步完成资料准备</h2>
      <ol>
        <li>下载模板，填写店铺、商品、SKU、资料类型和提交人；资料文件只放已核实的商品事实。</li>
        <li>上传后先查看识别到的字段和待补充项；请勿上传客户会话、手机号、地址、订单或支付信息。</li>
        <li>确认无误后人工审核。审核通过的不可变版本才会供 AI 做质量分析，不会自动发布或修改回复。</li>
      </ol>
    </section>

    <section class="work-grid">
      <form class="card upload-form" @submit.prevent="submit">
        <h2>上传资料</h2>
        <label>店铺编码<input v-model.trim="form.store_code" required maxlength="96"></label>
        <label>商品编号<input v-model.trim="form.product_id" required maxlength="128"></label>
        <label>SKU 编号（可选）<input v-model.trim="form.sku_id" maxlength="128"></label>
        <label>资料类型<select v-model="form.material_type"><option v-for="type in materialTypes" :key="type" :value="type">{{ displayStatus(type) }}</option></select></label>
        <label>资料名称<input v-model.trim="form.display_name" required maxlength="256" placeholder="例如：积木商品规格说明"></label>
        <label>提交人<input v-model.trim="form.submitted_by" required maxlength="128" placeholder="填写运营人员姓名或账号"></label>
        <label>修正已有资料编号（可选）<input v-model.trim="form.material_id" maxlength="64" placeholder="修正时填写 KMT-...，系统会创建新版本"></label>
        <label>资料文件<input type="file" accept=".txt,.md,.csv,.json,.xlsx" required @change="onFileChange"><small>支持 .txt、.md、.csv、.json、.xlsx，单个文件最大 5 MB。</small></label>
        <p class="notice boundary">系统只保存受控运行时文件；不会自动脱敏、发布知识、训练模型、修改 Prompt 或向客户发送消息。</p>
        <p v-if="formError" class="notice error" role="alert">{{ formError }}</p>
        <p v-if="receipt" class="notice success" role="status">{{ receipt }}</p>
        <button class="button" :disabled="submitting || !file" type="submit">{{ submitting ? '正在识别资料…' : '上传并识别' }}</button>
      </form>

      <section class="card materials">
        <div class="section-heading"><div><h2>资料记录</h2><p>当前列表只显示元数据与识别摘要，不提供原始文件下载。</p></div><button class="button secondary" type="button" @click="load">刷新</button></div>
        <form class="filters" @submit.prevent="load"><label>店铺<input v-model.trim="filters.store_code"></label><label>商品<input v-model.trim="filters.product_id"></label><label>状态<select v-model="filters.material_status"><option value="">全部</option><option v-for="status in statuses" :key="status" :value="status">{{ displayStatus(status) }}</option></select></label><button class="button secondary" type="submit">筛选</button></form>
        <p v-if="loading" class="notice" role="status">正在读取资料记录…</p>
        <p v-else-if="listError" class="notice error" role="alert">{{ listError }}</p>
        <p v-else-if="materials.length === 0" class="notice">当前没有符合条件的资料记录。请先按左侧步骤上传一份已核实的商品资料。</p>
        <div v-else class="table-wrap"><table class="data-table"><thead><tr><th>资料</th><th>适用范围</th><th>识别结果</th><th>状态</th></tr></thead><tbody><tr v-for="item in materials" :key="`${item.material_id}-${item.revision}`"><td><button class="link-button" type="button" @click="choose(item)">{{ item.display_name }}</button><small>{{ item.material_id }} · v{{ item.revision }}</small></td><td>{{ item.store_code }}<small>{{ item.product_id }} / {{ item.sku_id || '全部 SKU' }}</small></td><td>{{ item.recognition_summary.detected_fields.join('、') || '未识别到字段' }}<small v-if="item.recognition_summary.missing_expected_fields.length">待补充：{{ item.recognition_summary.missing_expected_fields.join('、') }}</small></td><td><span class="badge">{{ displayStatus(item.material_status) }}</span></td></tr></tbody></table></div>
      </section>
    </section>

    <section v-if="selected" class="card review-panel">
      <div class="section-heading"><div><h2>人工核对：{{ selected.display_name }}</h2><p>版本 {{ selected.revision }} · {{ displayStatus(selected.material_status) }}</p></div><span class="badge">{{ displayStatus(selected.material_type) }}</span></div>
      <div class="review-grid"><div><h3>识别摘要</h3><p><strong>已识别：</strong>{{ selected.recognition_summary.detected_fields.join('、') || '未识别到字段' }}</p><p><strong>待补充：</strong>{{ selected.recognition_summary.missing_expected_fields.join('、') || '暂无明显缺口' }}</p><p class="notice boundary">{{ selected.recognition_summary.privacy_reminder }}</p><h3>核对摘录</h3><pre>{{ selected.analysis_text_preview }}</pre></div><div v-if="selected.material_status === 'RECOGNIZED'" class="review-form"><h3>审核决定</h3><label>审核人<input v-model.trim="review.reviewed_by" maxlength="128" placeholder="填写运营人员姓名或账号"></label><label>审核备注<textarea v-model.trim="review.review_note" maxlength="4000" placeholder="说明已核对的来源、缺口或拒绝原因"></textarea></label><button class="button" type="button" :disabled="reviewing || !review.reviewed_by || !review.review_note" @click="approve">{{ reviewing ? '提交中…' : '审核通过，交给 AI 分析' }}</button><button class="button secondary" type="button" :disabled="reviewing || !review.reviewed_by || !review.review_note" @click="reject">拒绝本次资料</button></div><div v-else><h3>审核记录</h3><p>{{ selected.review_note || '该资料尚未记录审核备注。' }}</p><details><summary>技术详情</summary><dl><div><dt>内容校验</dt><dd>{{ selected.content_hash }}</dd></div><div><dt>去标识化版本</dt><dd>{{ selected.redaction_version }}</dd></div><div><dt>文件名</dt><dd>{{ selected.original_filename }}</dd></div></dl></details></div></div>
    </section>
  </main>
</template>

<style scoped>
.guide { margin-bottom: 20px; background: #f8fbff; }.guide h2, .upload-form h2, .materials h2, .review-panel h2 { margin-top: 0; color: #172554; }.guide li { margin: 8px 0; line-height: 1.6; }.work-grid, .review-grid { display: grid; grid-template-columns: minmax(280px, .78fr) minmax(0, 1.5fr); gap: 20px; }.upload-form, .review-form { display: grid; align-content: start; gap: 12px; }.upload-form label, .filters label, .review-form label { display: grid; gap: 6px; color: #526279; font-size: 13px; }.upload-form input, .upload-form select, .review-form input, .review-form textarea, .filters input, .filters select { min-height: 38px; padding: 8px; border: 1px solid #cbd7e6; border-radius: 7px; font: inherit; }.review-form textarea { min-height: 108px; resize: vertical; }.upload-form small, small { display: block; margin-top: 4px; color: #64748b; }.boundary { color: #75570a; background: #fff8df; line-height: 1.55; }.section-heading { display: flex; justify-content: space-between; gap: 16px; align-items: start; }.section-heading p { margin: 5px 0 0; color: #617087; }.filters { display: flex; flex-wrap: wrap; align-items: end; gap: 10px; margin: 18px 0; }.link-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; text-align: left; cursor: pointer; }.review-panel { margin-top: 20px; }.review-grid { grid-template-columns: minmax(0, 1.35fr) minmax(260px, .75fr); }.review-grid h3 { margin-top: 0; color: #25466f; }.review-grid p, pre { line-height: 1.6; overflow-wrap: anywhere; white-space: pre-wrap; }pre { max-height: 330px; margin: 0; padding: 12px; overflow: auto; border-radius: 8px; background: #f4f7fb; font-size: 13px; }dl { display: grid; gap: 10px; }dt { color: #64748b; }dd { margin: 3px 0 0; overflow-wrap: anywhere; }@media (max-width: 980px) { .work-grid, .review-grid { grid-template-columns: 1fr; } }
</style>
