<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'

import {
  apiErrorMessage,
  listAdminExperienceCases,
  updateAdminExperienceCaseReview,
  type AdminExperienceCase,
  type ExperienceCaseReviewStatus,
} from '../api/client'
import { displayStatus } from '../presentation'

const cases = ref<AdminExperienceCase[]>([])
const selected = ref<AdminExperienceCase | null>(null)
const loading = ref(false)
const error = ref('')
const actionError = ref('')
const reviewNote = ref('')
const reviewedBy = ref('operations-test-operator')
const filters = reactive({
  store_code: '', product_id: '', sku_id: '', review_status: '', created_by: '', page: 1, size: 20,
})
const statuses: ExperienceCaseReviewStatus[] = ['NEW', 'REVIEWING', 'APPROVED', 'REJECTED']
const canReview = computed(() => selected.value !== null && reviewedBy.value.trim().length > 0 && !loading.value)

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const result = await listAdminExperienceCases(filters)
    cases.value = result.items
    if (selected.value) selected.value = result.items.find((item) => item.case_id === selected.value?.case_id) || selected.value
  } catch (reason: unknown) {
    cases.value = []
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

function choose(item: AdminExperienceCase): void {
  selected.value = item
  reviewNote.value = item.review_note || ''
  reviewedBy.value = item.reviewed_by || 'operations-test-operator'
  actionError.value = ''
}

async function transition(reviewStatus: ExperienceCaseReviewStatus): Promise<void> {
  if (!selected.value || !reviewedBy.value.trim()) return
  actionError.value = ''
  try {
    selected.value = await updateAdminExperienceCaseReview(selected.value.case_id, {
      review_status: reviewStatus,
      review_note: reviewNote.value || null,
      reviewed_by: reviewedBy.value.trim(),
    })
    await load()
  } catch (reason: unknown) {
    actionError.value = apiErrorMessage(reason)
  }
}

onMounted(load)
</script>

<template>
  <main class="page">
    <div class="page-header">
      <div>
        <h1>客服经验库</h1>
        <p>沉淀客服提交的真实案例。只有人工审核通过后才会形成受控评测快照；不会自动发布知识或修改提示词。</p>
      </div>
      <button class="button secondary" type="button" @click="load">刷新数据</button>
    </div>

    <form class="filters card" @submit.prevent="filters.page = 1; load()">
      <label>店铺<input v-model.trim="filters.store_code" /></label>
      <label>商品<input v-model.trim="filters.product_id" /></label>
      <label>SKU<input v-model.trim="filters.sku_id" /></label>
      <label>提交人<input v-model.trim="filters.created_by" /></label>
      <label>审核状态<select v-model="filters.review_status"><option value="">全部</option><option v-for="status in statuses" :key="status" :value="status">{{ displayStatus(status) }}</option></select></label>
      <button class="button" type="submit">筛选案例</button>
    </form>

    <p v-if="loading" class="notice" role="status">正在读取客服案例…</p>
    <p v-else-if="error" class="notice error" role="alert">暂时无法读取客服案例。{{ error }}</p>
    <p v-else-if="cases.length === 0" class="notice">样本不足：没有符合当前筛选条件的客服案例。请调整筛选条件或等待客服提交案例。</p>

    <section v-else class="case-grid">
      <div class="card table-wrap">
        <table class="data-table">
          <thead><tr><th>案例</th><th>店铺</th><th>商品 / SKU</th><th>提交人</th><th>审核状态</th></tr></thead>
          <tbody><tr v-for="item in cases" :key="`${item.case_id}-${item.revision}`">
            <td><button class="link-button" type="button" @click="choose(item)">{{ item.case_id }}</button><small>版本 {{ item.revision }}</small></td>
            <td>{{ item.store_code }}</td><td>{{ item.product_id || '未关联商品' }} / {{ item.sku_id || '未关联 SKU' }}</td>
            <td>{{ item.created_by }}</td><td><span class="badge">{{ displayStatus(item.review_status) }}</span></td>
          </tr></tbody>
        </table>
      </div>

      <aside v-if="selected" class="card detail">
        <h2>案例详情</h2>
        <dl>
          <div><dt>客户问题</dt><dd>{{ selected.question }}</dd></div>
          <div><dt>AI 回答</dt><dd>{{ selected.ai_answer }}</dd></div>
          <div><dt>客服最终回复</dt><dd>{{ selected.final_answer }}</dd></div>
          <div><dt>反馈类型</dt><dd>{{ displayStatus(selected.feedback_type) }}</dd></div>
          <div><dt>审核记录</dt><dd>{{ displayStatus(selected.review_status) }} / {{ selected.reviewed_by || '尚未审核' }}<br>{{ selected.reviewed_at || '尚未记录时间' }}</dd></div>
        </dl>
        <template v-if="selected.review_status === 'NEW' || selected.review_status === 'REVIEWING'">
          <label>试运行操作人标识<input v-model.trim="reviewedBy" aria-label="试运行操作人标识" /></label>
          <label>审核说明<textarea v-model="reviewNote" maxlength="4000" /></label>
          <p class="subtle">当前环境仅记录试运行操作人标识，尚未启用正式身份认证。</p>
          <p v-if="actionError" class="notice error" role="alert">{{ actionError }}</p>
          <div class="actions">
            <button v-if="selected.review_status === 'NEW'" class="button secondary" :disabled="!canReview" @click="transition('REVIEWING')">开始审核</button>
            <template v-else>
              <button class="button" :disabled="!canReview" @click="transition('APPROVED')">通过并生成评测快照</button>
              <button class="button danger" :disabled="!canReview" @click="transition('REJECTED')">拒绝案例</button>
            </template>
          </div>
        </template>
        <p v-else class="notice">此终态版本不可覆盖修改。{{ selected.review_status === 'APPROVED' ? '已通过案例可通过受控导出接口提供评测。' : '' }}</p>
      </aside>
      <aside v-else class="card detail"><h2>案例详情</h2><p>选择一条案例，查看提交内容和审核记录。</p></aside>
    </section>
  </main>
</template>

<style scoped>
.filters { display: flex; flex-wrap: wrap; align-items: end; gap: 12px; margin-bottom: 20px; padding: 16px; }
label { display: grid; gap: 5px; color: #526279; font-size: 13px; }
input, select, textarea { min-height: 38px; padding: 8px; border: 1px solid #cbd7e6; border-radius: 7px; font: inherit; }
textarea { min-height: 96px; resize: vertical; }
.case-grid { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(310px, 1fr); gap: 20px; }
.detail { display: grid; align-content: start; gap: 14px; }.detail h2 { margin: 0; color: #172554; }
dl { display: grid; gap: 12px; margin: 0; }dt { color: #526279; font-size: 12px; font-weight: 700; }
dd { margin: 4px 0 0; line-height: 1.5; white-space: pre-wrap; }.link-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; text-align: left; cursor: pointer; }
small, .subtle { color: #617087; font-size: 12px; }.actions { display: flex; flex-wrap: wrap; gap: 10px; }.danger { border-color: #9c3434; background: #9c3434; }
@media (max-width: 900px) { .case-grid { grid-template-columns: 1fr; } }
</style>
