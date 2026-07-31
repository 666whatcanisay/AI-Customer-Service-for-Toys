<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { useRoute } from 'vue-router'

import {
  apiErrorMessage,
  getKnowledgeMaterial,
  listKnowledgeMaterials,
  reviewKnowledgeMaterial,
  type KnowledgeMaterial,
  type KnowledgeMaterialDetail,
} from '../api/client'

const route = useRoute()
const materials = ref<KnowledgeMaterial[]>([])
const selected = ref<KnowledgeMaterialDetail | null>(null)
const loading = ref(true)
const reviewing = ref(false)
const error = ref('')
const receipt = ref('')
const review = reactive({ reviewed_by: '', review_note: '' })

async function load(): Promise<void> {
  loading.value = true
  error.value = ''
  try {
    const productId = typeof route.query.product === 'string' ? route.query.product : undefined
    const result = await listKnowledgeMaterials({
      product_id: productId,
      material_status: 'RECOGNIZED',
      size: 100,
    })
    materials.value = result.items
    if (selected.value && !materials.value.some((item) => item.material_id === selected.value?.material_id)) {
      selected.value = null
    }
  } catch (reason: unknown) {
    materials.value = []
    selected.value = null
    error.value = apiErrorMessage(reason)
  } finally {
    loading.value = false
  }
}

async function choose(item: KnowledgeMaterial): Promise<void> {
  error.value = ''
  receipt.value = ''
  try {
    selected.value = await getKnowledgeMaterial(item.material_id)
  } catch (reason: unknown) {
    selected.value = null
    error.value = apiErrorMessage(reason)
  }
}

async function submitReview(decision: 'APPROVE_FOR_ANALYSIS' | 'REJECT'): Promise<void> {
  if (!selected.value || reviewing.value) return
  reviewing.value = true
  error.value = ''
  receipt.value = ''
  try {
    const reviewed = await reviewKnowledgeMaterial(selected.value.material_id, {
      revision: selected.value.revision,
      decision,
      reviewed_by: review.reviewed_by,
      review_note: review.review_note,
    })
    receipt.value = decision === 'APPROVE_FOR_ANALYSIS'
      ? `资料已审核通过：${reviewed.display_name}`
      : `资料已拒绝并保留审核记录：${reviewed.display_name}`
    selected.value = null
    review.review_note = ''
    await load()
  } catch (reason: unknown) {
    error.value = apiErrorMessage(reason)
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
        <p class="eyebrow">商品知识治理</p>
        <h1>知识审核队列</h1>
        <p>审核“商品知识维护”提交的待审核资料；R009 Excel 导入仍在“资料上传与审核”页面处理。</p>
      </div>
      <RouterLink class="button secondary" to="/knowledge-editor">返回商品知识维护</RouterLink>
    </div>

    <p class="notice boundary">审核通过只允许资料进入受控质量分析，不会直接写入 R009 正式商品字段，也不会自动发布 RAG、启用客服、修改 Prompt 或执行客户动作。</p>
    <p v-if="error" class="notice error" role="alert">{{ error }}</p>
    <p v-if="receipt" class="notice success" role="status">{{ receipt }}</p>

    <section class="review-grid">
      <section class="card queue">
        <div class="section-heading">
          <div><h2>待审核资料</h2><p>仅展示状态为“已识别待审核”的资料。</p></div>
          <button class="button secondary" type="button" @click="load">刷新</button>
        </div>
        <p v-if="loading" class="notice" role="status">正在读取审核队列…</p>
        <p v-else-if="materials.length === 0" class="notice">当前没有待审核知识资料。</p>
        <div v-else class="material-list">
          <article v-for="item in materials" :key="`${item.material_id}-${item.revision}`" class="material-card">
            <div class="material-heading">
              <strong>{{ item.display_name }}</strong>
              <span class="badge">已识别待审核</span>
            </div>
            <p>商品：{{ item.product_id }}</p>
            <p>已识别字段：{{ item.recognition_summary.detected_fields.join('、') || '无' }}</p>
            <p>提交人：{{ item.submitted_by }} · 修订 {{ item.revision }}</p>
            <button class="text-button" type="button" @click="choose(item)">查看并审核</button>
          </article>
        </div>
      </section>

      <section class="card review-panel">
        <template v-if="selected">
          <div class="section-heading">
            <div><h2>人工核对</h2><p>{{ selected.display_name }}</p></div>
            <span class="badge">已识别待审核</span>
          </div>
          <h3>识别摘要</h3>
          <p><strong>已识别：</strong>{{ selected.recognition_summary.detected_fields.join('、') || '无' }}</p>
          <p><strong>待补充：</strong>{{ selected.recognition_summary.missing_expected_fields.join('、') || '暂无明显缺口' }}</p>
          <pre>{{ selected.analysis_text_preview }}</pre>
          <label>审核人<input v-model.trim="review.reviewed_by" maxlength="128" placeholder="填写运营人员姓名或账号"></label>
          <label>审核备注<textarea v-model.trim="review.review_note" maxlength="4000" placeholder="说明已核对的来源、范围与决定"></textarea></label>
          <div class="actions">
            <button class="button" type="button" :disabled="reviewing || !review.reviewed_by || !review.review_note" @click="submitReview('APPROVE_FOR_ANALYSIS')">审核通过</button>
            <button class="button secondary" type="button" :disabled="reviewing || !review.reviewed_by || !review.review_note" @click="submitReview('REJECT')">拒绝本次资料</button>
          </div>
        </template>
        <p v-else class="notice">从左侧选择一条资料后核对并审核。</p>
      </section>
    </section>
  </main>
</template>

<style scoped>
.eyebrow { margin: 0 0 6px; color: #2b5fcc; font-size: 12px; font-weight: 800; letter-spacing: .08em; }
.boundary { margin-bottom: 18px; color: #75570a; background: #fff8df; }
.review-grid { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(320px, .9fr); gap: 20px; }
.section-heading, .material-heading { display: flex; justify-content: space-between; gap: 16px; align-items: start; }
.section-heading h2, .review-panel h3 { margin-top: 0; color: #172554; }
.section-heading p { margin: 5px 0 0; color: #617087; }
.material-list { display: grid; gap: 10px; margin-top: 16px; }
.material-card { padding: 14px; border: 1px solid #dbe4ef; border-radius: 10px; }
.material-card p { margin: 7px 0; color: #617087; font-size: 13px; overflow-wrap: anywhere; }
.text-button { padding: 0; border: 0; color: #285493; background: transparent; font: inherit; cursor: pointer; }
.review-panel { display: grid; align-content: start; gap: 12px; }
.review-panel label { display: grid; gap: 6px; color: #526279; font-size: 13px; }
.review-panel input, .review-panel textarea { min-height: 41px; padding: 9px; border: 1px solid #cbd7e6; border-radius: 8px; font: inherit; }
.review-panel textarea { min-height: 108px; resize: vertical; }
.review-panel pre { max-height: 260px; margin: 0; padding: 12px; overflow: auto; border-radius: 8px; background: #f4f7fb; white-space: pre-wrap; overflow-wrap: anywhere; }
.actions { display: flex; flex-wrap: wrap; gap: 10px; }
@media (max-width: 900px) { .review-grid { grid-template-columns: 1fr; } }
</style>
